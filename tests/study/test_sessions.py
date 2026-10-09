"""Choosing cards for a test and saving answers (spec 6.2, 6.7)."""

import hashlib
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from study import services
from study.models import Direction, ReviewLog, ReviewState, StudyDirection, StudyScope
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm


@pytest.fixture
def tree(user, en, cs):
    """Angličtina › Seriály › HIMYM, Big Bang Theory."""
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    series = vocabulary.create_deck(user, "Seriály", parent=english)
    himym = vocabulary.create_deck(user, "HIMYM", parent=series)
    bbt = vocabulary.create_deck(user, "Big Bang Theory", parent=series)
    return {"english": english, "series": series, "himym": himym, "bbt": bbt}


def add(deck, foreign, native, **extra):
    return vocabulary.add_term(deck, foreign=foreign, native=native, **extra).term


def start(user, *decks, **options):
    return services.start_session(user, decks, **options)


def play(session, rating="ok", limit=100):
    """Answer every card with the same rating. Returns the shown cards as (word, direction)."""
    shown = []
    for _ in range(limit):
        card = services.next_card(session)
        if card is None:
            return shown
        shown.append((card.term.main_foreign, card.direction))
        services.record_answer(session, card, rating)
    raise AssertionError("The session did not end")


# Starting


def test_session_needs_a_deck(user):
    with pytest.raises(ValidationError):
        services.start_session(user, [])


def test_session_cannot_use_other_users_deck(other_user, tree):
    with pytest.raises(ValidationError):
        start(other_user, tree["himym"])


def test_session_directions(user, tree):
    assert start(user, tree["himym"], direction=StudyDirection.F2N).directions == [Direction.F2N]
    assert start(user, tree["himym"]).directions == [Direction.F2N, Direction.N2F]


# Which cards come


def test_child_decks_are_included_and_shared_words_come_once(user, tree):
    hello = add(tree["himym"], "hello", "ahoj")
    DeckTerm.objects.create(deck=tree["bbt"], term=hello)
    add(tree["bbt"], "physics", "fyzika")

    session = start(user, tree["series"], direction=StudyDirection.F2N)

    assert sorted(play(session)) == [("hello", "F2N"), ("physics", "F2N")]


def test_only_chosen_decks(user, tree):
    add(tree["himym"], "hello", "ahoj")
    add(tree["bbt"], "physics", "fyzika")

    session = start(user, tree["bbt"], direction=StudyDirection.F2N)

    assert play(session) == [("physics", "F2N")]


def test_mixed_direction_shows_both_sides(user, tree):
    add(tree["himym"], "hello", "ahoj")

    session = start(user, tree["himym"])

    assert sorted(play(session)) == [("hello", "F2N"), ("hello", "N2F")]


def test_due_cards_first_from_the_oldest_then_new_ones(user, tree):
    add(tree["himym"], "new", "nový")
    old = add(tree["himym"], "old", "starý")
    older = add(tree["himym"], "older", "starší")
    now = timezone.now()
    ReviewState.objects.filter(term=old).update(due_at=now - timedelta(days=1))
    ReviewState.objects.filter(term=older).update(due_at=now - timedelta(days=5))

    session = start(user, tree["himym"], direction=StudyDirection.F2N)

    # Cards tested before go first (in random order), new cards after them
    shown = [word for word, _ in play(session)]
    assert sorted(shown[:2]) == ["old", "older"]
    assert shown[2] == "new"


def test_cards_not_due_yet_do_not_come(user, tree):
    later = add(tree["himym"], "later", "později")
    ReviewState.objects.filter(term=later).update(due_at=timezone.now() + timedelta(days=3))

    session = start(user, tree["himym"])

    assert play(session) == []


def shuffled(session, states):
    """The order the session must use: by the hash of its seed and the card (like Postgres)."""
    key = lambda state: hashlib.md5(f"{session.shuffle_seed}-{state.pk}".encode()).hexdigest()  # noqa: E731
    return [(state.term.main_foreign, state.direction) for state in sorted(states, key=key)]


def test_new_cards_come_in_random_order_of_the_test(user, tree):
    for word in ["one", "two", "three", "four", "five", "six"]:
        add(tree["himym"], word, word)
    states = list(ReviewState.objects.select_related("term"))

    first = start(user, tree["himym"])
    second = start(user, tree["himym"])
    second.shuffle_seed = first.shuffle_seed + 1
    second.save()

    # Each test has its own order; it stays the same while the test goes on
    assert services.next_card(first) == services.next_card(first)
    expected = shuffled(first, states)
    shown = play(first)
    assert sorted(shown) == sorted(expected)
    assert shuffled(second, states) != expected


def test_both_directions_are_not_always_next_to_each_other(user, tree):
    words = [f"word{index}" for index in range(10)]
    for word in words:
        add(tree["himym"], word, word)

    shown = play(start(user, tree["himym"]))

    # Before the random order, the other direction always came right after one card
    gaps = []
    for word in words:
        places = [index for index, (shown_word, _) in enumerate(shown) if shown_word == word]
        gaps.append(places[1] - places[0])
    assert max(gaps) > 2


def test_answered_card_does_not_come_again_in_due_scope(user, tree):
    add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"], direction=StudyDirection.F2N)

    assert len(play(session, "ok")) == 1


def test_dont_know_comes_back_when_due(user, tree):
    add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"], direction=StudyDirection.F2N)
    card = services.next_card(session)
    services.record_answer(session, card, "dontknow")

    assert services.next_card(session) is None
    later = timezone.now() + timedelta(minutes=11)
    assert services.next_card(session, now=later).term.main_foreign == "hello"


def test_scope_all_shows_every_card_once(user, tree):
    later = add(tree["himym"], "later", "později")
    add(tree["himym"], "new", "nový")
    ReviewState.objects.filter(term=later).update(due_at=timezone.now() + timedelta(days=30))

    session = start(user, tree["himym"], direction=StudyDirection.F2N, scope=StudyScope.ALL)

    assert sorted(word for word, _ in play(session)) == ["later", "new"]


def test_max_cards(user, tree):
    for word in ["one", "two", "three"]:
        add(tree["himym"], word, word)

    session = start(user, tree["himym"], direction=StudyDirection.F2N, max_cards=2)

    assert len(play(session)) == 2


def test_finished_session_gives_no_card(user, tree):
    add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"])

    services.finish_session(session)

    assert services.next_card(session) is None
    assert session.finished_at is not None


# Spacing


def test_same_word_not_twice_in_a_row(user, tree):
    add(tree["himym"], "hello", "ahoj")
    add(tree["himym"], "bye", "nashle")

    session = start(user, tree["himym"])
    words = [word for word, _ in play(session)]

    assert all(a != b for a, b in zip(words, words[1:], strict=False))


def test_two_meanings_not_in_a_row(user, tree):
    add(tree["himym"], "palm", "dlaň")
    add(tree["himym"], "palm", "palma")
    add(tree["himym"], "hello", "ahoj")

    session = start(user, tree["himym"], direction=StudyDirection.F2N)
    # Whatever the random order is: after one "palm" the other one waits while "hello" is left
    palm = ReviewState.objects.filter(term__main_foreign="palm", direction="F2N").first()
    services.record_answer(session, palm, "ok")

    assert services.next_card(session).term.main_foreign == "hello"


def test_same_word_is_allowed_when_nothing_else_is_left(user, tree):
    add(tree["himym"], "hello", "ahoj")

    session = start(user, tree["himym"])

    assert len(play(session)) == 2


# Saving answers


def test_record_answer_saves_state_log_and_counters(user, tree):
    hello = add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"], direction=StudyDirection.F2N)
    card = services.next_card(session)

    log = services.record_answer(session, card, "think", think_ms="4200", decide_ms=800)

    card.refresh_from_db()
    assert card.last_rating == "think"
    assert card.due_at is not None
    assert log.term == hello
    assert log.session == session
    assert (log.rating, log.rating_label, log.result) == ("think", "Vím po zamyšlení", "correct")
    assert log.chosen_interval == timedelta(days=3)
    assert (log.think_ms, log.decide_ms) == (4200, 800)
    assert (session.answered, session.correct) == (1, 1)


def test_partial_and_wrong_are_not_counted_as_correct(user, tree):
    add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"])

    services.record_answer(session, services.next_card(session), "partial")
    services.record_answer(session, services.next_card(session), "dontknow")

    assert (session.answered, session.correct) == (2, 0)


@pytest.mark.parametrize("value", [None, "", "abc", -5, 5 * 60 * 1000 + 1])
def test_strange_times_are_not_saved(user, tree, value):
    add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"])

    log = services.record_answer(session, services.next_card(session), "ok", think_ms=value)

    assert log.think_ms is None


def test_card_from_other_deck_is_refused(user, tree):
    physics = add(tree["bbt"], "physics", "fyzika")
    session = start(user, tree["himym"])
    card = ReviewState.objects.get(term=physics, direction=Direction.F2N)

    with pytest.raises(ValidationError):
        services.record_answer(session, card, "ok")
    assert not ReviewLog.objects.exists()


def test_card_in_wrong_direction_is_refused(user, tree):
    hello = add(tree["himym"], "hello", "ahoj")
    session = start(user, tree["himym"], direction=StudyDirection.F2N)
    card = ReviewState.objects.get(term=hello, direction=Direction.N2F)

    with pytest.raises(ValidationError):
        services.record_answer(session, card, "ok")


def test_rating_counts_in_every_deck_of_the_word(user, tree):
    hello = add(tree["himym"], "hello", "ahoj")
    DeckTerm.objects.create(deck=tree["bbt"], term=hello)
    first = start(user, tree["himym"], direction=StudyDirection.F2N)
    play(first, "ok")

    # The same word in the other deck is not due any more
    second = start(user, tree["bbt"], direction=StudyDirection.F2N)
    assert services.next_card(second) is None


# Summary


def test_session_summary(user, tree):
    for word in ["one", "two", "three"]:
        add(tree["himym"], word, word)
    session = start(user, tree["himym"], direction=StudyDirection.F2N)
    shown = []
    for rating in ["ok", "dontknow", "partial"]:
        card = services.next_card(session)
        shown.append(card.term.main_foreign)
        services.record_answer(session, card, rating)

    summary = services.session_summary(session)

    assert summary["answered"] == 3
    assert {rating.key: count for rating, count in summary["counts"]} == {
        "ok": 1,
        "think": 0,
        "partial": 1,
        "dontknow": 1,
    }
    # The words rated 😵 and 😕 (the order of the test is random)
    assert sorted(term.main_foreign for term in summary["problem_terms"]) == sorted(shown[1:])
