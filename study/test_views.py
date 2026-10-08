"""Test pages: setup, card, answer, summary, retry."""

import pytest
from django.urls import reverse

from vocabulary import services as vocabulary

from . import services
from .models import ReviewLog, ReviewState, StudySession

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
    assert f'value="{himym.pk}" checked' in html
    assert response.context["form"].initial["direction"] == "N2F"


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

    assert 'class="card-main">hello<' in html
    assert "😎" in html and "😵" in html
    assert "7 dní" in html and "10 min" in html
    assert "Vím, opakovat za 7 dní" in html
    assert 'id="legend"' in html


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

    response = answer(logged_client, session, "think")
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="card"' in html
    assert 'class="card-main">bye<' in html
    assert "<html" not in html
    log = ReviewLog.objects.get()
    assert (log.term, log.rating, log.think_ms, log.decide_ms) == (words[0], "think", 1500, 400)


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
    answer(logged_client, session, "dontknow")

    html = logged_client.get(reverse("study:summary", args=[session.pk])).content.decode()
    assert "Ohodnocené kartičky: 2" in html
    assert "Na zopakování" in html
    assert "bye" in html

    response = logged_client.post(reverse("study:retry", args=[session.pk]))
    retry = StudySession.objects.exclude(pk=session.pk).get()
    assert response.url == reverse("study:card", args=[retry.pk])
    assert list(retry.terms.all()) == [words[1]]


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
