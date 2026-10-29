"""Test pages: setup, card, answer, summary, retry."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from dictionary.models import ErrorReport
from study import services
from study.models import Direction, ReviewLog, ReviewState, StudySession
from vocabulary import services as vocabulary

HTMX = {"HX-Request": "true"}


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def himym(user, en, cs):
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    return vocabulary.create_deck(user, "HIMYM", parent=english)


@pytest.fixture
def words(himym):
    return [
        vocabulary.add_term(himym, foreign="hello", native="ahoj").term,
        vocabulary.add_term(himym, foreign="bye", native="nashle").term,
    ]


def new_session(user, deck, direction="F2N"):
    return services.start_session(user, [deck], direction=direction)


def answer(client, session, rating="ok", **extra):
    state = services.next_card(session)
    data = {
        "state": state.pk,
        "reviews_count": state.reviews_count,
        "rating": rating,
        "think_ms": "1500",
        "decide_ms": "400",
        **extra,
    }
    return client.post(reverse("study:answer", args=[session.pk]), data, headers=HTMX)


# Setup


def test_setup_page_preselects_deck_and_direction(logged_client, user, himym):
    user.default_direction = "N2F"
    user.save()

    response = logged_client.get(reverse("study:new") + f"?deck={himym.pk}")
    html = response.content.decode()

    assert response.status_code == 200
    # Only this deck, no tree: a hidden field and a link to change it
    assert f'<input type="hidden" name="decks" value="{himym.pk}">' in html
    assert f'name="decks" value="{himym.pk}" checked' not in html
    assert f"?deck={himym.pk}&amp;pick=1" in html
    assert response.context["form"].initial["direction"] == "N2F"


def test_setup_change_link_shows_the_tree_with_the_deck_ticked(logged_client, himym):
    response = logged_client.get(reverse("study:new") + f"?deck={himym.pk}&pick=1")

    html = response.content.decode()
    assert f'value="{himym.pk}" checked' in html
    assert response.context["single_deck"] is None


def test_setup_of_a_deck_tells_its_subdecks(logged_client, user, himym):
    vocabulary.create_deck(user, "S01", parent=himym)
    vocabulary.create_deck(user, "S02", parent=himym)

    response = logged_client.get(reverse("study:new") + f"?deck={himym.pk}")

    assert "a 2 podslovníky" in response.content.decode()


def test_setup_shows_how_many_cards_there_are(logged_client, user, himym, words):
    # One word was tested and is due again, the other one is new
    state = ReviewState.objects.get(term=words[0], direction="F2N")
    state.due_at = state.last_reviewed_at = timezone.now() - timedelta(days=1)
    state.save()

    response = logged_client.get(reverse("study:new") + f"?deck={himym.pk}")
    counts = response.context["counts"]

    # The user's default direction is mixed: every word is two cards
    assert counts == {"due": 1, "new": 3, "all": 4}
    html = response.content.decode()
    assert "jen k opakování a nová (4)" in html
    assert "Prázdné = bez omezení." in html


def test_counts_follow_the_form(logged_client, himym, words):
    response = logged_client.get(
        reverse("study:counts"),
        {"decks": [himym.pk], "direction": "F2N", "scope": "all", "max_cards": "5"},
        headers=HTMX,
    )

    assert response.context["counts"] == {"due": 0, "new": 2, "all": 2}
    html = response.content.decode()
    assert 'id="test-options"' in html
    assert re.search(r'value="all"[^>]*checked', html)
    assert 'value="5"' in html


def test_directions_are_named_by_the_languages_of_the_deck(logged_client, himym):
    response = logged_client.get(reverse("study:new") + f"?deck={himym.pk}")

    choices = dict(response.context["form"].fields["direction"].choices)
    assert choices == {
        "F2N": "EN → CS",
        "N2F": "CS → EN",
        "MIXED": "EN ⇄ CS",
    }


def test_directions_of_decks_with_other_languages_have_general_names(
    logged_client, user, himym, es, cs
):
    spanish = vocabulary.create_deck(user, "Español", foreign_language=es, native_language=cs)

    response = logged_client.get(
        reverse("study:counts"), {"decks": [himym.pk, spanish.pk], "direction": "MIXED"}
    )

    choices = dict(response.context["form"].fields["direction"].choices)
    assert choices["MIXED"] == "cizí ⇄ rodný"
    # The part with the directions and the counts is loaded again after every change
    assert 'id="test-options"' in response.content.decode()


def test_counts_ignore_other_users_decks(client, other_user, himym, words):
    client.force_login(other_user)

    response = client.get(reverse("study:counts"), {"decks": [himym.pk], "direction": "F2N"})

    assert response.context["counts"] == {"due": 0, "new": 0, "all": 0}


def test_setup_starts_session(logged_client, himym, words):
    response = logged_client.post(
        reverse("study:new"), {"decks": [himym.pk], "direction": "MIXED", "scope": "due"}
    )

    session = StudySession.objects.get()
    assert response.url == reverse("study:card", args=[session.pk])
    assert list(session.decks.all()) == [himym]


def test_setup_needs_a_deck(logged_client, himym):
    response = logged_client.post(reverse("study:new"), {"direction": "MIXED", "scope": "due"})

    assert "Vyber aspoň jeden slovník" in response.content.decode()
    assert not StudySession.objects.exists()


def test_setup_refuses_other_users_deck(client, other_user, himym):
    client.force_login(other_user)

    client.post(reverse("study:new"), {"decks": [himym.pk], "direction": "MIXED", "scope": "due"})

    assert not StudySession.objects.exists()


# Card


def test_card_page_shows_question_and_buttons(logged_client, user, himym, words):
    session = new_session(user, himym)

    html = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()

    # The order is random, so the first card can be either word
    first = services.next_card(session).term.main_foreign
    assert f'class="card-main">{first}<' in html
    assert "😎" in html and "😵" in html
    # When the word comes again is hidden by default (Settings)
    assert 'class="rating-interval"' not in html
    assert 'aria-label="Vím"' in html
    # The help window opens by itself at the first test
    assert 'id="legend"' in html
    assert "data-open-first" in html


def test_card_page_names_the_direction_by_languages(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)

    html = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()

    # "EN → CS" with the arrow as an icon, not the generic "cizí → rodný"
    first, second = ("EN", "CS") if state.direction == Direction.F2N else ("CS", "EN")
    assert f'{first}<svg class="arrow"' in html
    assert f"{second}</small>" in html
    assert "cizí → rodný" not in html and "rodný → cizí" not in html


def test_card_page_shows_intervals_when_the_user_wants(logged_client, user, himym, words):
    user.show_intervals = True
    user.save()
    session = new_session(user, himym)

    html = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()

    assert "7 dní" in html and "10 min" in html
    assert "Vím, opakovat za 7 dní" in html


def test_help_does_not_open_by_itself_after_it_was_closed(logged_client, user, himym, words):
    response = logged_client.post(reverse("study:help_seen"))

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.seen_test_help
    session = new_session(user, himym)
    html = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()
    # Still there for the "?" button, only not opened by itself
    assert 'id="legend"' in html
    assert "data-open-first" not in html


def test_help_seen_needs_post(logged_client, user):
    assert logged_client.get(reverse("study:help_seen")).status_code == 405


def test_empty_session_goes_to_summary(logged_client, user, himym):
    session = new_session(user, himym)

    response = logged_client.get(reverse("study:card", args=[session.pk]))

    assert response.url == reverse("study:summary", args=[session.pk])


def test_other_users_session_gives_404(client, other_user, user, himym, words):
    session = new_session(user, himym)
    client.force_login(other_user)

    assert client.get(reverse("study:card", args=[session.pk])).status_code == 404
    assert client.get(reverse("study:summary", args=[session.pk])).status_code == 404


# Answer


def test_answer_returns_next_card(logged_client, user, himym, words):
    session = new_session(user, himym)
    first = services.next_card(session).term
    other = words[1] if first == words[0] else words[0]

    response = answer(logged_client, session, "think")
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="card"' in html
    assert f'class="card-main">{other.main_foreign}<' in html
    assert "<html" not in html
    log = ReviewLog.objects.get()
    assert (log.term, log.rating, log.think_ms, log.decide_ms) == (first, "think", 1500, 400)


def test_last_answer_redirects_to_summary(logged_client, user, himym, words):
    session = new_session(user, himym)
    answer(logged_client, session)

    response = answer(logged_client, session)

    assert response["HX-Redirect"] == reverse("study:summary", args=[session.pk])
    session.refresh_from_db()
    assert session.finished_at is not None


def test_same_answer_twice_is_saved_once(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)
    data = {"state": state.pk, "reviews_count": state.reviews_count, "rating": "ok"}
    url = reverse("study:answer", args=[session.pk])

    logged_client.post(url, data, headers=HTMX)
    logged_client.post(url, data, headers=HTMX)

    assert ReviewLog.objects.count() == 1
    assert ReviewState.objects.get(pk=state.pk).reviews_count == 1


def test_unknown_rating_is_refused(logged_client, user, himym, words):
    session = new_session(user, himym)

    response = answer(logged_client, session, "great")

    assert response.status_code == 400
    assert not ReviewLog.objects.exists()


def test_answer_without_htmx_redirects(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)

    response = logged_client.post(
        reverse("study:answer", args=[session.pk]),
        {"state": state.pk, "reviews_count": state.reviews_count, "rating": "ok"},
    )

    assert response.url == reverse("study:card", args=[session.pk])


def test_finish_button(logged_client, user, himym, words):
    session = new_session(user, himym)

    response = logged_client.post(reverse("study:finish", args=[session.pk]))

    session.refresh_from_db()
    assert response.url == reverse("study:summary", args=[session.pk])
    assert session.finished_at is not None


# Summary and retry


def test_summary_and_retry(logged_client, user, himym, words):
    session = new_session(user, himym)
    answer(logged_client, session, "ok")
    # The order is random: the second card is the one rated 😵
    wrong = services.next_card(session).term
    answer(logged_client, session, "dontknow")

    html = logged_client.get(reverse("study:summary", args=[session.pk])).content.decode()
    assert "Ohodnocené kartičky: 2" in html
    assert "Na zopakování" in html
    assert wrong.main_foreign in html

    response = logged_client.post(reverse("study:retry", args=[session.pk]))
    retry = StudySession.objects.exclude(pk=session.pk).get()
    assert response.url == reverse("study:card", args=[retry.pk])
    assert list(retry.terms.all()) == [wrong]


def test_retry_without_mistakes_stays_on_summary(logged_client, user, himym, words):
    session = new_session(user, himym)
    answer(logged_client, session, "ok")

    response = logged_client.post(reverse("study:retry", args=[session.pk]))

    assert response.url == reverse("study:summary", args=[session.pk])
    assert StudySession.objects.count() == 1


def test_start_buttons_on_dashboard_and_deck(logged_client, himym):
    dashboard = logged_client.get(reverse("dashboard")).content.decode()
    deck = logged_client.get(reverse("vocabulary:deck_detail", args=[himym.pk])).content.decode()

    assert reverse("study:new") in dashboard
    assert f"{reverse('study:new')}?deck={himym.pk}" in deck


# Edit the word during a test (✏️)


def test_card_links_to_edit_of_its_word(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)
    deck_term = state.term.deck_terms.get()

    html = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()

    url = reverse("vocabulary:term_edit", args=[himym.pk, deck_term.pk])
    assert f'data-edit-url="{url}?test={session.pk}"' in html
    assert 'data-action="edit-term"' in html


def test_edit_from_test_goes_back_to_the_same_card(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)
    deck_term = state.term.deck_terms.get()
    url = reverse("vocabulary:term_edit", args=[himym.pk, deck_term.pk]) + f"?test={session.pk}"

    page = logged_client.get(url).content.decode()
    assert "Uložit a zpět do testu" in page
    assert "Neukládat a zpět do testu" in page
    assert "Odebrat z tohoto slovníku" not in page

    response = logged_client.post(url, {"foreign": "helo", "native": "ahoj"})

    assert response.url == reverse("study:card", args=[session.pk])
    state.term.refresh_from_db()
    assert state.term.main_foreign == "helo"
    # The card was not rated, so it comes again, now fixed
    assert services.next_card(session).pk == state.pk
    assert ReviewLog.objects.filter(session=session).count() == 0


def test_report_from_test_goes_back_to_the_same_card(logged_client, user, himym, words):
    session = new_session(user, himym)
    state = services.next_card(session)
    deck_term = state.term.deck_terms.get()
    url = reverse("vocabulary:term_report", args=[himym.pk, deck_term.pk]) + f"?test={session.pk}"

    card = logged_client.get(reverse("study:card", args=[session.pk])).content.decode()
    assert f'data-report-url="{url}"' in card and 'data-action="report-term"' in card
    # "Cancel" goes to the test too
    back = reverse("study:card", args=[session.pk])
    assert f'href="{back}"' in logged_client.get(url).content.decode()

    response = logged_client.post(url, {"kind": "translation"})

    assert response.url == back
    assert ErrorReport.objects.get().term == state.term
    # The card was not rated, so it comes again
    assert services.next_card(session).pk == state.pk


def test_edit_without_test_or_with_finished_test_goes_to_the_deck(
    logged_client, user, himym, words
):
    session = new_session(user, himym)
    services.finish_session(session)
    deck_term = words[0].deck_terms.get()
    url = reverse("vocabulary:term_edit", args=[himym.pk, deck_term.pk])

    for address in (url, f"{url}?test={session.pk}", f"{url}?test=x"):
        response = logged_client.post(address, {"foreign": "hello", "native": "ahoj"})
        assert response.url == reverse("vocabulary:deck_detail", args=[himym.pk])


# The card: one big word and one sentence on each side


def _sides(html):
    front = html[html.index('class="card-front"') : html.index('class="card-back"')]
    back = html[html.index('class="card-back"') : html.index('class="card-show"')]
    return front, back


def test_card_shows_one_sentence_on_each_side(logged_client, user, himym):
    vocabulary.add_term(
        himym,
        foreign="glad",
        native="rád",
        context_sentence="I'm {glad} you came.",
        context_sentence_native="Jsem {ráda}, že jsi přišel.",
    )
    session = new_session(user, himym, direction="N2F")

    front, back = _sides(
        logged_client.get(reverse("study:card", args=[session.pk])).content.decode()
    )

    # Native → foreign: in front the Czech sentence, no English sentence with a gap
    assert "<mark>ráda</mark>" in front and "you came" not in front and "___" not in front
    # The back: the English sentence with the word marked, not the Czech one again
    assert "<mark>glad</mark> you came" in back and "přišel" not in back


def test_card_without_translation_of_the_sentence_has_a_gap(logged_client, user, himym):
    vocabulary.add_term(
        himym, foreign="glad", native="rád", context_sentence="I'm {glad} you came."
    )
    session = new_session(user, himym, direction="N2F")

    front, back = _sides(
        logged_client.get(reverse("study:card", args=[session.pk])).content.decode()
    )

    assert "___" in front and "glad" not in front
    assert "<mark>glad</mark> you came" in back


def test_foreign_to_native_card_shows_the_translation_of_the_sentence_on_the_back(
    logged_client, user, himym
):
    vocabulary.add_term(
        himym,
        foreign="glad",
        native="rád",
        context_sentence="I'm {glad} you came.",
        context_sentence_native="Jsem {ráda}, že jsi přišel.",
    )
    session = new_session(user, himym, direction="F2N")

    front, back = _sides(
        logged_client.get(reverse("study:card", args=[session.pk])).content.decode()
    )

    assert "<mark>glad</mark> you came" in front and "přišel" not in front
    assert "<mark>ráda</mark>" in back and "you came" not in back
