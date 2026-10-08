from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from .models import Result, ReviewState
from .ratings import MAX_INTERVAL, RATINGS, get_rating
from .services import apply_rating, next_interval, preview_intervals, round_interval

PRAGUE = ZoneInfo("Europe/Prague")


def days(n):
    return timedelta(days=n)


def new_state():
    # Not saved, the rules do not need the database
    return ReviewState()


# The buttons


def test_buttons_order_and_keys():
    assert [rating.key for rating in RATINGS] == ["ok", "think", "partial", "dontknow"]
    assert [rating.emoji for rating in RATINGS] == ["😎", "🤔", "😕", "😵"]
    assert [rating.hotkey for rating in RATINGS] == ["1", "2", "3", "4"]


def test_unknown_rating():
    with pytest.raises(ValueError):
        get_rating("great")


# Rounding


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        (timedelta(minutes=10), timedelta(minutes=10)),
        (timedelta(hours=23), timedelta(hours=23)),
        (days(7.5), days(8)),
        (days(7.4), days(7)),
        (days(312.5), days(313)),
        (days(20), days(20)),
    ],
)
def test_round_interval(interval, expected):
    assert round_interval(interval) == expected


# Next interval


def test_new_word_gets_the_minimum():
    assert next_interval(get_rating("ok"), None) == days(7)
    assert next_interval(get_rating("think"), None) == days(3)
    assert next_interval(get_rating("partial"), None) == days(1)
    assert next_interval(get_rating("dontknow"), None) == timedelta(minutes=10)


def test_interval_grows():
    assert next_interval(get_rating("ok"), days(7)) == days(28)
    assert next_interval(get_rating("think"), days(3)) == days(8)  # 7.5 rounded


def test_interval_never_below_minimum():
    # After "partial" (1 day): 1 × 4 = 4 days, but "ok" gives at least 7
    assert next_interval(get_rating("ok"), days(1)) == days(7)
    assert next_interval(get_rating("think"), timedelta(minutes=10)) == days(3)


def test_interval_never_above_one_year():
    assert next_interval(get_rating("ok"), days(112)) == MAX_INTERVAL
    assert next_interval(get_rating("think"), days(365)) == MAX_INTERVAL


def test_fixed_buttons_ignore_the_last_interval():
    assert next_interval(get_rating("partial"), days(280)) == days(1)
    assert next_interval(get_rating("dontknow"), days(280)) == timedelta(minutes=10)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ok", [7, 28, 112, 365, 365]),
        ("think", [3, 8, 20, 50, 125, 313, 365]),
    ],
)
def test_repeated_rating_sequence(key, expected):
    state = new_state()
    now = datetime(2026, 10, 8, 9, 0, tzinfo=PRAGUE)
    seen = []
    for _ in expected:
        interval = apply_rating(state, key, now=now)
        seen.append(interval / days(1))
        now = state.due_at
    assert seen == expected


# The example from the spec (6.3): ahoj → hello


def test_spec_example_ahoj():
    state = new_state()
    steps = [
        # (date of the test, button, expected interval, next date, streak, lapses)
        (datetime(2026, 10, 8, 9, 0), "ok", days(7), datetime(2026, 10, 15, 9, 0), 1, 0),
        (datetime(2026, 10, 15, 9, 0), "ok", days(28), datetime(2026, 11, 12, 9, 0), 2, 0),
        (datetime(2026, 11, 12, 9, 0), "ok", days(112), datetime(2027, 3, 4, 9, 0), 3, 0),
        (datetime(2027, 3, 4, 9, 0), "think", days(280), datetime(2027, 12, 9, 9, 0), 4, 0),
        (datetime(2027, 12, 9, 9, 0), "partial", days(1), datetime(2027, 12, 10, 9, 0), 0, 0),
        (datetime(2027, 12, 10, 9, 0), "ok", days(7), datetime(2027, 12, 17, 9, 0), 1, 0),
    ]
    for when, key, interval, next_date, streak, lapses in steps:
        now = when.replace(tzinfo=PRAGUE)
        assert apply_rating(state, key, now=now) == interval
        assert state.due_at == next_date.replace(tzinfo=PRAGUE)
        assert (state.correct_streak, state.lapses) == (streak, lapses)
    assert state.reviews_count == 6
    assert state.last_rating == "ok"


# Counters


def test_apply_rating_sets_state():
    state = new_state()
    now = datetime(2026, 10, 8, 9, 0, tzinfo=PRAGUE)

    apply_rating(state, "dontknow", now=now)

    assert state.due_at == now + timedelta(minutes=10)
    assert state.last_reviewed_at == now
    assert state.last_rating == "dontknow"
    assert state.last_interval == timedelta(minutes=10)
    assert (state.reviews_count, state.correct_streak, state.lapses) == (1, 0, 1)


def test_partial_breaks_streak_but_is_not_a_lapse():
    state = new_state()
    apply_rating(state, "ok")
    apply_rating(state, "ok")

    apply_rating(state, "partial")

    assert state.correct_streak == 0
    assert state.lapses == 0
    assert get_rating("partial").result == Result.PARTIAL


def test_wrong_resets_growth():
    state = new_state()
    apply_rating(state, "ok")  # 7
    apply_rating(state, "ok")  # 28

    apply_rating(state, "dontknow")  # 10 min
    assert apply_rating(state, "ok") == days(7)


# Preview under the emoji


def test_preview_for_new_card():
    preview = {rating.key: interval for rating, interval in preview_intervals(new_state())}

    assert preview == {
        "ok": days(7),
        "think": days(3),
        "partial": days(1),
        "dontknow": timedelta(minutes=10),
    }


def test_preview_for_known_card():
    state = new_state()
    state.last_interval = days(112)

    preview = [interval for _rating, interval in preview_intervals(state)]

    assert preview == [days(365), days(280), days(1), timedelta(minutes=10)]
