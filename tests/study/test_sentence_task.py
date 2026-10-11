"""End of a test: the word that does not stick, with a form to add a sentence to it."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from dictionary.providers import get_example_sentence
from study import services
from study.models import Direction, Result, ReviewLog
from tests.conftest import lexicon_entry
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm

RESULTS = {"ok": Result.CORRECT, "partial": Result.PARTIAL, "dontknow": Result.WRONG}


@pytest.fixture
def deck(user, en, cs):
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    return vocabulary.create_deck(user, "HIMYM", parent=english)


def history(user, term, ratings):
    """Old answers of the word, the first one the oldest."""
    start = timezone.now() - timedelta(days=len(ratings) + 1)
    for index, rating in enumerate(ratings):
        ReviewLog.objects.create(
            user=user,
            term=term,
            direction=Direction.F2N,
            rating=rating,
            rating_label=rating,
            result=RESULTS[rating],
            chosen_interval=timedelta(days=1),
            reviewed_at=start + timedelta(days=index),
        )


def finished_test(user, deck):
    """A finished test where every word was answered once with 😵."""
    session = services.start_session(user, [deck], direction="F2N")
    while (card := services.next_card(session)) is not None:
        services.record_answer(session, card, "dontknow")
    return session


# Choosing the word


def test_word_that_fails_often_is_chosen(user, deck):
    palm = vocabulary.add_term(deck, foreign="palm", native="dlaň").term
    history(user, palm, ["dontknow", "ok", "dontknow", "partial"])

    hard = services.hard_word_without_sentence(finished_test(user, deck))

    assert hard["deck_term"].term == palm
    # 4 old answers and the one of this test: 4 of 5 were not right
    assert (hard["bad"], hard["total"]) == (4, 5)


def test_word_forgotten_once_is_not_chosen(user, deck):
    hello = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    history(user, hello, ["ok", "ok", "ok", "ok", "ok", "ok"])

    assert services.hard_word_without_sentence(finished_test(user, deck)) is None


def test_only_the_last_answers_count(user, deck):
    # Failed a lot long ago, but the last answers are good: the word was learned
    hello = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    history(user, hello, ["dontknow"] * 6 + ["ok"] * 7)

    assert services.hard_word_without_sentence(finished_test(user, deck)) is None


def test_word_with_too_few_answers_is_not_chosen(user, deck):
    vocabulary.add_term(deck, foreign="hello", native="ahoj")

    assert services.hard_word_without_sentence(finished_test(user, deck)) is None


def test_word_with_a_sentence_is_skipped(user, deck):
    with_sentence = vocabulary.add_term(
        deck, foreign="palm", native="dlaň", context_sentence="She read my palm."
    ).term
    without = vocabulary.add_term(deck, foreign="bet", native="sázka").term
    history(user, with_sentence, ["dontknow"] * 5)
    history(user, without, ["dontknow", "ok", "dontknow"])

    hard = services.hard_word_without_sentence(finished_test(user, deck))

    assert hard["deck_term"].term == without


def test_the_worst_word_is_chosen(user, deck):
    bad = vocabulary.add_term(deck, foreign="bet", native="sázka").term
    worse = vocabulary.add_term(deck, foreign="palm", native="dlaň").term
    history(user, bad, ["dontknow", "ok", "ok"])
    history(user, worse, ["dontknow", "dontknow", "dontknow"])

    hard = services.hard_word_without_sentence(finished_test(user, deck))

    assert hard["deck_term"].term == worse


# Summary page and saving


def test_summary_offers_the_word_and_saves_the_sentence(client, user, deck):
    deck_term = vocabulary.add_term(deck, foreign="palm", native="dlaň")
    history(user, deck_term.term, ["dontknow", "dontknow"])
    session = finished_test(user, deck)
    client.force_login(user)

    html = client.get(reverse("study:summary", args=[session.pk])).content.decode()
    assert "Tohle slovíčko ti nejde" in html
    assert 'name="context_sentence_native"' in html

    url = reverse("study:add_sentence", args=[session.pk, deck_term.pk])
    response = client.post(
        url,
        {
            "context_sentence": "She can read from her {}.",
            "context_sentence_native": "Umí číst z dlaně.",
        },
        headers={"HX-Request": "true"},
    )

    assert "je uložená" in response.content.decode()
    deck_term.refresh_from_db()
    assert deck_term.context_sentence == "She can read from her {}."
    assert deck_term.context_sentence_native == "Umí číst z dlaně."


def test_sentence_is_needed(client, user, deck):
    deck_term = vocabulary.add_term(deck, foreign="palm", native="dlaň")
    session = finished_test(user, deck)
    client.force_login(user)

    url = reverse("study:add_sentence", args=[session.pk, deck_term.pk])
    response = client.post(url, {"context_sentence": " "}, headers={"HX-Request": "true"})

    assert "Napiš aspoň větu" in response.content.decode()
    assert DeckTerm.objects.get().context_sentence == ""


def test_other_users_word_gives_404(client, user, other_user, deck):
    deck_term = vocabulary.add_term(deck, foreign="palm", native="dlaň")
    session = finished_test(user, deck)
    client.force_login(other_user)

    url = reverse("study:add_sentence", args=[session.pk, deck_term.pk])

    assert client.post(url, {"context_sentence": "x"}).status_code == 404


# Example from the dictionary


def test_example_of_the_right_meaning(user, deck, lexicon):
    lexicon(
        lexicon_entry(
            "house",
            "noun",
            [
                ("dům", "The {house} was very old.", "{Dům} byl velmi starý."),
                ("house", "He likes {house} music.", "Má rád {house}."),
            ],
        )
    )
    house = vocabulary.add_term(deck, foreign="house", native="dům").term
    music = vocabulary.add_term(deck, foreign="house", native="house").term

    # The sentence keeps its braces: the user's sentences mark the word the same way
    assert get_example_sentence(house) == {
        "text": "The {house} was very old.",
        "translation": "{Dům} byl velmi starý.",
    }
    assert get_example_sentence(music)["text"] == "He likes {house} music."


def test_no_example_for_other_meaning(user, deck, lexicon):
    lexicon(lexicon_entry("palm", "noun", [("palma", "A tall {palm}.", "Vysoká {palma}.")]))
    hand = vocabulary.add_term(deck, foreign="palm", native="dlaň").term

    assert get_example_sentence(hand) is None


def test_summary_shows_example_without_braces(client, user, deck, lexicon):
    lexicon(lexicon_entry("palm", "noun", [("dlaň", "She read my {palm}.", "Četla mi z {dlaně}.")]))
    deck_term = vocabulary.add_term(deck, foreign="palm", native="dlaň")
    history(user, deck_term.term, ["dontknow", "dontknow"])
    session = finished_test(user, deck)
    client.force_login(user)

    html = client.get(reverse("study:summary", args=[session.pk])).content.decode()

    assert "<em>She read my palm.</em> → Četla mi z dlaně." in html
    assert 'data-text="She read my {palm}."' in html


# Coloured dots of the last answers


def test_dots_for_each_direction_from_the_oldest(user, deck):
    palm = vocabulary.add_term(deck, foreign="palm", native="dlaň").term
    history(user, palm, ["ok", "partial", "dontknow"])

    rows = {row["direction"]: row for row in services.answer_dots(palm)}

    assert [dot["key"] for dot in rows["F2N"]["dots"]] == ["ok", "partial", "dontknow"]
    assert not any(dot["hidden"] for dot in rows["F2N"]["dots"])
    assert rows["F2N"]["percent"] == 33
    assert rows["N2F"]["total"] == 0


def test_older_dots_are_hidden_behind_plus(user, deck):
    palm = vocabulary.add_term(deck, foreign="palm", native="dlaň").term
    history(user, palm, ["ok"] * 2 + ["dontknow"] * 10)

    row = services.answer_dots(palm)[0]

    # The last 8 are shown; "+4" hides the 2× 😎 and 2× 😵 before them
    assert [dot["hidden"] for dot in row["dots"]].count(False) == 8
    assert row["more"] == 4
    assert row["more_title"] == "4 starších: 2× 😵 · 2× 😎"
    assert row["older"] == 0


def test_at_most_thirty_dots(user, deck):
    palm = vocabulary.add_term(deck, foreign="palm", native="dlaň").term
    history(user, palm, ["dontknow"] * 35)

    row = services.answer_dots(palm)[0]

    assert len(row["dots"]) == services.DOTS_MAX
    assert row["older"] == 5


def test_summary_and_word_page_show_dots(client, user, deck):
    deck_term = vocabulary.add_term(deck, foreign="palm", native="dlaň")
    history(user, deck_term.term, ["dontknow"] * 9)
    session = finished_test(user, deck)
    client.force_login(user)

    summary = client.get(reverse("study:summary", args=[session.pk])).content.decode()
    detail_url = reverse("vocabulary:term_detail", args=[deck.pk, deck_term.pk])
    detail = client.get(detail_url).content.decode()

    # 10 answers: 8 dots and "+2" that can be opened
    assert summary.count('class="dot dot-dontknow"') == 10
    assert 'data-action="more-dots"' in summary
    assert ">+2<" in summary
    # The word page: all dots and the ring with the share of correct answers
    assert 'class="dots-ring" style="--percent: 0"' in detail
