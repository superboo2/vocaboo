"""Statistics page: totals, words over time, the last tests and the words that are hard.

Everything is counted from the words (Term.created_at), the answers (ReviewLog) and the review
states, nothing extra is stored. The user has hundreds or thousands of rows at most, so the
numbers are counted in Python from simple queries.
"""

import random
from collections import Counter
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext, pgettext, pgettext_lazy

from vocabulary.models import DeckTerm, Term
from vocabulary.services import deck_names, deck_path

from .models import (
    Direction,
    Result,
    ReviewLog,
    ReviewState,
    StudyDirection,
    StudyScope,
    StudySession,
)
from .ratings import RATINGS

# A word counts as known ("umíš") when every direction it was tested in was right this many
# times in a row (the interval is then a week or more). A direction never tested does not count.
KNOWN_STREAK = 2


def is_known(streaks):
    """Known: streaks (right answers in a row) of the directions the word was tested in, all
    at least KNOWN_STREAK. The one rule for the word page, the statistics and "learned"."""
    streaks = list(streaks)
    return bool(streaks) and all(streak >= KNOWN_STREAK for streak in streaks)


# The table of recent tests: how many tests, and the days of the line above it
RECENT_TESTS = 10
TESTS_DAYS = 14
WEEKDAY_SHORT = [
    pgettext_lazy("weekday short", "Mon"),
    pgettext_lazy("weekday short", "Tue"),
    pgettext_lazy("weekday short", "Wed"),
    pgettext_lazy("weekday short", "Thu"),
    pgettext_lazy("weekday short", "Fri"),
    pgettext_lazy("weekday short", "Sat"),
    pgettext_lazy("weekday short", "Sun"),
]

# Days in the bar chart of the dashboard (today is the last one)
WEEK_DAYS = 7

# Periods of the fun facts: key in the URL (?period=30) → (days or None for all, name)
PERIODS = {
    "7": (7, gettext_lazy("7 days")),
    "30": (30, gettext_lazy("30 days")),
    "all": (None, gettext_lazy("All")),
}
# The statistics page shows the fun facts of the last 30 days (enough words for the cards and
# still about now); the periods stay for the code and the tests
DEFAULT_PERIOD = "30"
# "roller_coaster" needs this many changes between right and wrong, "rush" a "don't know at
# all" faster than this (ms)
SWITCHES = 3
RUSH_MS = 3000
# The kinds of cards in the order of the statistics page. The dashboard shows
# DASHBOARD_FACTS of them, mixed by the date of the day it is about (see hard_words).
STATS_FACTS = [
    "slow",
    "one_way",
    "again",
    "enemy",
    "mix_up",
    "forget",
    "roller_coaster",
    "rush",
    "longest",
    "oldest",
]
# The title of each kind of card (the kinds above are only keys)
FACT_TITLES = {
    "slow": gettext_lazy("You think longest about"),
    "one_way": gettext_lazy("Only one way"),
    "again": gettext_lazy("Over and over"),
    "enemy": gettext_lazy("Worst enemy"),
    "mix_up": gettext_lazy("You mix up"),
    "forget": gettext_lazy("You forget"),
    "roller_coaster": gettext_lazy("Roller coaster"),
    "rush": gettext_lazy("Too fast"),
    "longest": gettext_lazy("Longest you struggle with"),
    "oldest": gettext_lazy("Learning it longest"),
}
DASHBOARD_FACTS = 3
# "again" shows a word only after this many attempts in the whole history
REPEAT_ATTEMPTS = 3


def _week_start(day):
    return day - timedelta(days=day.weekday())


def _local_day(moment):
    return timezone.localtime(moment).date()


def user_statistics(user, now=None, period=DEFAULT_PERIOD):
    now = now or timezone.now()
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    today = _local_day(now)
    terms = list(Term.objects.filter(owner=user).values_list("created_at", "main_foreign", "pk"))
    logs = _logs(user)
    known = known_words(user)
    tested = {row[5] for row in logs}

    return {
        "totals": _totals(terms, logs, known, tested, today),
        "words_chart": _words_chart(terms, today),
        "streak": _streak(logs, today),
        "tests": recent_tests(user, now),
        "facts": _facts(user, logs, now, period),
        "period": period,
        "periods": [(key, name) for key, (_days, name) in PERIODS.items()],
        "has_terms": bool(terms),
        "has_logs": bool(logs),
    }


def known_words(user):
    """Words the user knows ("umíš", is_known): every tested direction right KNOWN_STREAK
    times in a row. The lowest streak of the tested directions decides."""
    return (
        ReviewState.objects.filter(term__owner=user, last_reviewed_at__isnull=False)
        .values("term_id")
        .annotate(lowest=Min("correct_streak"))
        .filter(lowest__gte=KNOWN_STREAK)
        .count()
    )


def recent_tests(user, now=None):
    """The last tests with at least one answer, one row each, and how often tests are done.

    Cards are answers: with both directions one word is two cards, and each one is rated.
    """
    now = now or timezone.now()
    tests = _tests(user)
    rows = _test_rows(user, tests[:RECENT_TESTS])
    recent = list(
        tests.filter(started_at__gte=now - timedelta(days=TESTS_DAYS)).values_list(
            "cards", flat=True
        )
    )
    summary = ""
    if recent:
        average = round(sum(recent) / len(recent))
        tests_text = ngettext(
            "%(count)s test in %(days)s days", "%(count)s tests in %(days)s days", len(recent)
        ) % {"count": len(recent), "days": TESTS_DAYS}
        average_text = ngettext(
            "on average %(count)s word", "on average %(count)s words", average
        ) % {"count": average}
        summary = f"{tests_text} · {average_text}"
    return {"rows": rows, "summary": summary}


def today_overview(user, now=None):
    """Today on the dashboard, only good news of the tests, each with its last WEEK_DAYS days
    for a small bar chart (today is the last day):

    - first right: words right (😎 or 🤔, any direction) for the first time ever,
    - learned: words that became known ("umíš", is_known) for the first time: every tested
      direction right KNOWN_STREAK times in a row (the same as on the statistics page),
    - tested: different words in the tests (both directions count once),
    - minutes: the length of the tests (to the last answer), by the day the test began.
    """
    now = now or timezone.now()
    today = _local_day(now)
    days = [today - timedelta(days=back) for back in range(WEEK_DAYS - 1, -1, -1)]
    midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight - timedelta(days=WEEK_DAYS - 1)

    first_right = Counter(
        _local_day(first)
        for first in ReviewLog.objects.filter(user=user, result=Result.CORRECT)
        .values("term_id")
        .annotate(first=Min("reviewed_at"))
        .filter(first__gte=since)
        .values_list("first", flat=True)
    )
    learned = Counter()
    # Right answers in a row of each tested direction of a word: {term: {direction: streak}}
    in_a_row = {}
    known = set()
    for term_id, direction, result, reviewed_at in (
        ReviewLog.objects.filter(user=user)
        .order_by("reviewed_at", "pk")
        .values_list("term_id", "direction", "result", "reviewed_at")
    ):
        streaks = in_a_row.setdefault(term_id, {})
        streaks[direction] = streaks.get(direction, 0) + 1 if result == Result.CORRECT else 0
        if term_id not in known and is_known(streaks.values()):
            known.add(term_id)
            if reviewed_at >= since:
                learned[_local_day(reviewed_at)] += 1
    tested = Counter(
        day
        for day, _term_id in {
            (_local_day(reviewed_at), term_id)
            for reviewed_at, term_id in ReviewLog.objects.filter(
                user=user, reviewed_at__gte=since
            ).values_list("reviewed_at", "term_id")
        }
    )
    spent = Counter()
    for started, last in (
        _tests(user)
        .filter(started_at__gte=since)
        .annotate(last_answer=Max("logs__reviewed_at"))
        .values_list("started_at", "last_answer")
    ):
        spent[_local_day(started)] += (last - started).total_seconds() / 60
    minutes = Counter({day: round(value) for day, value in spent.items()})

    def metric(key, icon, values, label, help_text, unit="%(value)s"):
        top = max(values[day] for day in days) or 1
        return {
            "key": key,
            "icon": icon,
            "value": unit % {"value": values[today]},
            "label": label,
            # The tooltip of the number: what exactly is counted
            "help": help_text,
            "bars": [
                {
                    "value": unit % {"value": values[day]},
                    "height": f"{100 * values[day] / top:.0f}",
                    "label": (
                        pgettext("weekday short", "today")
                        if day == today
                        else str(WEEKDAY_SHORT[day.weekday()])
                    ),
                    "title": _short_date(day),
                    "today": day == today,
                }
                for day in days
            ],
        }

    return {
        "metrics": [
            metric(
                "tested",
                "📚",
                tested,
                ngettext("word in tests", "words in tests", tested[today]),
                _(
                    "Different words that were in today's tests. A word in both directions "
                    "counts once."
                ),
            ),
            metric(
                "first",
                "🎯",
                first_right,
                _("right for the first time"),
                _(
                    "Words answered 😎 or 🤔 today for the first time ever, in any direction. "
                    "Each word counts once."
                ),
            ),
            metric(
                "learned",
                "🎓",
                learned,
                ngettext("word learned", "words learned", learned[today]),
                _(
                    "Words that today became “known” for the first time: right twice in a row "
                    "foreign → native. The second right answer comes only after an interval, "
                    "so for new words in a few days at the earliest."
                ),
            ),
            metric(
                "minutes",
                "⏱️",
                minutes,
                _("time in tests"),
                _("How long today's tests took (from the start of a test to its last answer)."),
                _("%(value)s min"),
            ),
        ],
    }


def _tests(user):
    """Tests with at least one answer, the newest first. Counted from the answers, not from
    the counters of the test: answers of deleted words are deleted too, the counters stay."""
    return (
        StudySession.objects.filter(user=user)
        .annotate(
            cards=Count("logs", distinct=True),
            correct_cards=Count("logs", filter=Q(logs__result=Result.CORRECT), distinct=True),
        )
        .filter(cards__gt=0)
        .order_by("-started_at", "-pk")
    )


def _test_rows(user, tests):
    sessions = list(
        tests.prefetch_related("decks__foreign_language", "decks__native_language").annotate(
            words=Count("logs__term", distinct=True),
            last_answer=Max("logs__reviewed_at"),
            retry=Count("terms", distinct=True),
        )
    )
    counts = Counter()
    for session_id, rating, count in (
        ReviewLog.objects.filter(session__in=sessions)
        .values_list("session_id", "rating")
        .annotate(count=Count("pk"))
    ):
        counts[session_id, rating] = count
    names = deck_names(user)
    return [_test_row(session, counts, names) for session in sessions]


def _test_row(session, counts, names):
    started = timezone.localtime(session.started_at)
    decks = list(session.decks.all())
    foreign, native = pgettext("language", "foreign"), pgettext("language", "native")
    if decks:
        foreign = decks[0].foreign_language.code.upper()
        native = decks[0].native_language.code.upper()
    direction = {
        StudyDirection.F2N: f"{foreign} → {native}",
        StudyDirection.N2F: f"{native} → {foreign}",
    }.get(session.direction, f"{foreign} → {native} + {native} → {foreign}")
    if session.scope == StudyScope.ALL:
        scope = pgettext("test scope", "all")
    else:
        scope = pgettext("test scope", "due + new")
    if session.retry:
        scope = pgettext("test scope", "wrong again")
    finished = session.finished_at is not None or (
        session.max_cards is not None and session.cards >= session.max_cards
    )
    minutes = round((session.last_answer - session.started_at).total_seconds() / 60)
    ratings = [{"rating": rating, "count": counts[session.pk, rating.key]} for rating in RATINGS]
    percent = round(100 * session.correct_cards / session.cards)
    return {
        "session": session,
        "when": f"{WEEKDAY_SHORT[started.weekday()]} {_short_date(started)}",
        "time": f"{started:%H:%M}",
        "paths": [deck_path(deck.pk, names) for deck in decks],
        "direction": direction,
        "scope": scope,
        "limit": _("max %(count)s") % {"count": session.max_cards} if session.max_cards else "",
        "cards": session.cards,
        "ratings": ratings,
        "percent": percent,
        "finished": finished,
        "time_spent": _minutes(minutes),
    }


def _minutes(minutes):
    if minutes < 1:
        return _("< 1 min")
    if minutes < 60:
        return _("%(count)s min") % {"count": minutes}
    return _("%(hours)s h %(minutes)s min") % {"hours": minutes // 60, "minutes": minutes % 60}


def _short_date(day):
    """Day and month, e.g. "18. 10." in Czech."""
    return _("%(month)s/%(day)s") % {"day": day.day, "month": day.month}


def hard_words(user, now=None):
    """The cards "Co ti včera / naposledy nešlo" for the dashboard.

    They are about the last day with a test before today, so they do not change during the
    day (today's tests show tomorrow) nor during a pause. The kinds are mixed by the date of
    that day: another day of tests shows other kinds. Returns {"day", "items"}; no day, no
    items when there was no test before today.
    """
    now = now or timezone.now()
    last = (
        ReviewLog.objects.filter(user=user, reviewed_at__lt=_day_start(_local_day(now)))
        .order_by("-reviewed_at")
        .values_list("reviewed_at", flat=True)
        .first()
    )
    if last is None:
        return {"day": None, "items": []}
    day = _local_day(last)
    kinds = list(STATS_FACTS)
    random.Random(day.toordinal()).shuffle(kinds)
    items = _facts(user, _logs(user), now, None, kinds=kinds, day=day)["items"]
    return {"day": day, "items": items[:DASHBOARD_FACTS]}


def _day_start(day):
    """Midnight at the start of a local day."""
    return timezone.make_aware(datetime.combine(day, time.min))


def _logs(user):
    return list(
        ReviewLog.objects.filter(user=user)
        .order_by("reviewed_at", "pk")
        .values_list(
            "reviewed_at", "result", "rating", "think_ms", "decide_ms", "term_id", "direction"
        )
    )


def _totals(terms, logs, known, tested, today):
    week = _week_start(today)
    added_this_week = sum(1 for created, _word, _pk in terms if _local_day(created) >= week)
    answers_this_week = sum(1 for log in logs if _local_day(log[0]) >= week)
    return {
        "words": len(terms),
        "added_this_week": added_this_week,
        "known": known,
        "learning": len(tested & {pk for _created, _word, pk in terms}) - known,
        "new": len({pk for _created, _word, pk in terms} - tested),
        "answers": len(logs),
        "answers_this_week": answers_this_week,
    }


def _words_chart(terms, today):
    """All words over time, from the day of the first word: by days at the start, then by
    weeks, months and quarters, so the chart always has a few points and no empty start."""
    days = sorted(_local_day(created) for created, _word, _pk in terms)
    first = min(days[0], today) if days else today
    span = (today - first).days
    if span < CHART_DAYS:
        unit, starts = "day", [first + timedelta(days=n) for n in range(span + 1)]
    elif span < CHART_WEEKS_DAYS:
        unit, starts = "week", _steps(_week_start(first), today, lambda d: d + timedelta(weeks=1))
    elif span < CHART_MONTHS_DAYS:
        unit, starts = "month", _steps(first.replace(day=1), today, lambda d: _add_months(d, 1))
    else:
        quarter = first.replace(month=(first.month - 1) // 3 * 3 + 1, day=1)
        unit, starts = "quarter", _steps(quarter, today, lambda d: _add_months(d, 3))
    nexts = [*starts[1:], today + timedelta(days=1)]
    totals = [sum(1 for day in days if day < end) for end in nexts]
    chart = _line_chart([_bucket_label(start, unit) for start in starts], totals)
    since = _("%(month)s/%(day)s/%(year)s") % {
        "day": first.day,
        "month": first.month,
        "year": first.year,
    }
    chart["subtitle"] = _("Total words %(unit)s since %(date)s") % {
        "unit": UNIT_NAMES[unit],
        "date": since,
    }
    return chart


# The words chart: by days up to 2 weeks after the first word, by weeks up to 4 months, by
# months up to 2 years, then by quarters
CHART_DAYS = 14
CHART_WEEKS_DAYS = 122
CHART_MONTHS_DAYS = 730
UNIT_NAMES = {
    "day": gettext_lazy("by day"),
    "week": gettext_lazy("by week"),
    "month": gettext_lazy("by month"),
    "quarter": gettext_lazy("by quarter"),
}
MONTHS_SHORT = [
    pgettext_lazy("month short", "Jan"),
    pgettext_lazy("month short", "Feb"),
    pgettext_lazy("month short", "Mar"),
    pgettext_lazy("month short", "Apr"),
    pgettext_lazy("month short", "May"),
    pgettext_lazy("month short", "Jun"),
    pgettext_lazy("month short", "Jul"),
    pgettext_lazy("month short", "Aug"),
    pgettext_lazy("month short", "Sep"),
    pgettext_lazy("month short", "Oct"),
    pgettext_lazy("month short", "Nov"),
    pgettext_lazy("month short", "Dec"),
]


def _steps(start, today, step):
    """Starts of the days, weeks … from start up to today."""
    starts = [start]
    while step(starts[-1]) <= today:
        starts.append(step(starts[-1]))
    return starts


def _add_months(day, months):
    month = day.month - 1 + months
    return day.replace(year=day.year + month // 12, month=month % 12 + 1, day=1)


def _bucket_label(start, unit):
    if unit in ("day", "week"):
        return _short_date(start)
    if unit == "month":
        return f"{MONTHS_SHORT[start.month - 1]} {start.year}"
    return _("Q%(quarter)s %(year)s") % {"quarter": (start.month - 1) // 3 + 1, "year": start.year}


def _nice_top(value):
    """A round top of the y axis: 7 -> 8, 63 -> 80, 230 -> 250."""
    if value <= 4:
        return 4
    step = 10 ** (len(str(int(value))) - 1)
    for factor in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= factor * step:
            return int(factor * step)
    return int(10 * step)


def _line_chart(labels, values, most_labels=5):
    """A simple line chart: a point for each label and the y axis with 5 round values.

    Positions are percents of the drawing area (0 = left / top): the SVG draws the line in a
    0–100 box stretched to the page, the dots and labels are HTML placed by the same percents.
    A value None breaks the line. One point sits in the middle.
    """
    top = _nice_top(max((value for value in values if value is not None), default=0))
    last = len(labels) - 1

    def left_of(index):
        return 50 if last == 0 else 100 * index / last

    points = []
    segments = []
    segment = []
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        if value is None:
            if segment:
                segments.append(segment)
            segment = []
            continue
        left = left_of(index)
        y = 100 - 100 * value / top
        points.append({"left": f"{left:.2f}", "top": f"{y:.2f}", "title": f"{label}: {value}"})
        segment.append(f"{left:.2f},{y:.2f}")
    if segment:
        segments.append(segment)
    ticks = [{"label": str(top * part // 4), "top": f"{100 - 25 * part:.0f}"} for part in range(5)]
    # At most a few labels under the axis, evenly from the last one back, so they do not touch
    every = max(1, -(-len(labels) // most_labels))
    shown = [
        {"label": label, "left": f"{left_of(index):.2f}"}
        for index, label in enumerate(labels)
        if (last - index) % every == 0
    ]
    return {
        "points": points,
        "segments": [" ".join(segment) for segment in segments],
        "ticks": ticks,
        "labels": shown,
    }


def _streak(logs, today):
    """Days in a row with at least one answer: now (today or up to yesterday) and the longest."""
    days = sorted({_local_day(log[0]) for log in logs})
    longest = current = 0
    previous = None
    for day in days:
        current = current + 1 if previous == day - timedelta(days=1) else 1
        longest = max(longest, current)
        previous = day
    if not days or days[-1] < today - timedelta(days=1):
        current = 0
    return {
        "current": current,
        "longest": longest,
        "current_text": _days(current),
        "longest_text": _days(longest),
    }


def _facts(user, logs, now, period, kinds=None, day=None):
    """The "nej" words that are hard: each one shows a word with its translation.

    A word is hard when in the period it had an answer "vůbec nevím" or "napůl" and it is
    still not known (some direction has fewer than KNOWN_STREAK right answers in a row).
    One word is shown only once, the next fact takes the next word in its order.

    With a day (the dashboard) the period is that one day and everything is as it was at its
    end: later answers are left out, so the cards stay the same.
    """
    if day is not None:
        since = _day_start(day)
        logs = [log for log in logs if log[0] < _day_start(day + timedelta(days=1))]
    else:
        days = PERIODS[period][0]
        since = now - timedelta(days=days) if days else None
    window = [log for log in logs if since is None or log[0] >= since]
    wrong = Counter()
    attempts = Counter()
    think = {}
    bad_directions = {}
    # The fastest "vůbec nevím" of a word, and how many times it went between right and wrong
    fast_wrong = {}
    switches = Counter()
    last_right = {}
    for _reviewed, result, _rating, think_ms, _decide, term_id, direction in window:
        attempts[term_id] += 1
        right = result == Result.CORRECT
        if result == Result.WRONG:
            wrong[term_id] += 1
            if think_ms:
                fast_wrong[term_id] = min(think_ms, fast_wrong.get(term_id, think_ms))
        if not right:
            bad_directions.setdefault(term_id, set()).add(direction)
        if think_ms:
            think.setdefault(term_id, []).append(think_ms)
        key = (term_id, direction)
        if key in last_right and last_right[key] != right:
            switches[term_id] += 1
        last_right[key] = right

    # Attempts of a word in the whole history (for "again")
    all_attempts = Counter(log[5] for log in logs)

    # Forgotten = a wrong answer after KNOWN_STREAK right ones in a row (the whole history
    # is needed for the streak, only the wrong answers in the period count)
    forgotten = Counter()
    in_a_row = Counter()
    for reviewed_at, result, _rating, _think, _decide, term_id, direction in logs:
        key = (term_id, direction)
        if result == Result.CORRECT:
            in_a_row[key] += 1
            continue
        if in_a_row[key] >= KNOWN_STREAK and (since is None or reviewed_at >= since):
            forgotten[term_id] += 1
        in_a_row[key] = 0

    streaks = {}
    if day is not None:
        # Right in a row at the end of that day, from the answers up to then
        for (term_id, direction), streak in in_a_row.items():
            if term_id in bad_directions:
                streaks.setdefault(term_id, {})[direction] = streak
    else:
        for term_id, direction, streak in ReviewState.objects.filter(
            term_id__in=bad_directions
        ).values_list("term_id", "direction", "correct_streak"):
            streaks.setdefault(term_id, {})[direction] = streak
    hard_ids = [
        term_id
        for term_id in bad_directions
        if any(streak < KNOWN_STREAK for streak in streaks.get(term_id, {}).values())
    ]
    first_deck_term = DeckTerm.objects.filter(term=OuterRef("pk")).order_by("pk")[:1]
    terms = {
        term.pk: term
        for term in Term.objects.filter(owner=user, pk__in=hard_ids)
        .select_related("foreign_language", "native_language")
        .annotate(
            # The word page is an address of the word in one deck: the first deck it is in
            deck_term_pk=Subquery(first_deck_term.values("pk")),
            deck_pk=Subquery(first_deck_term.values("deck_id")),
        )
        # Only words that are still in some deck (the link needs one)
        .filter(deck_term_pk__isnull=False)
    }
    if not terms:
        return {"items": [], "answered": bool(window)}

    def one_direction(term):
        """Right in one direction (last answer), wrong in the other one in the period."""
        directions = streaks.get(term.pk, {})
        return [
            direction
            for direction in bad_directions[term.pk]
            if directions.get(direction) == 0
            and any(other != direction and streak > 0 for other, streak in directions.items())
        ]

    # Two hard words with the same translation (borrow / lend – půjčit): the partner of each
    same_translation = {}
    for term in terms.values():
        key = (term.foreign_language_id, term.native_language_id, term.main_native.lower())
        same_translation.setdefault(key, []).append(term)
    partner = {}
    for group in same_translation.values():
        if len(group) > 1:
            for term in group:
                partner[term.pk] = next(other for other in group if other.pk != term.pk)

    def enemy_text(term):
        count = attempts[term.pk]
        return ngettext(
            "%(wrong)s× don't know at all out of %(count)s try",
            "%(wrong)s× don't know at all out of %(count)s tries",
            count,
        ) % {"wrong": wrong[term.pk], "count": count}

    hard = list(terms.values())
    # (kind, animal, colour of the stripe, words in order, why)
    candidates = [
        (
            "enemy",
            "🦈",
            "dontknow",
            sorted(
                (term for term in hard if wrong[term.pk]),
                key=lambda term: (-wrong[term.pk], -attempts[term.pk]),
            ),
            enemy_text,
        ),
        (
            "mix_up",
            "🦎",
            "partial",
            sorted(
                (term for term in hard if term.pk in partner),
                key=lambda term: -(wrong[term.pk] + wrong[partner[term.pk].pk]),
            ),
            lambda term: _("same translation, keep getting mixed up"),
        ),
        (
            "one_way",
            "🦀",
            "think",
            [term for term in hard if one_direction(term)],
            lambda term: _directions_text(term, one_direction(term)[0]),
        ),
        (
            "forget",
            "🐿️",
            "dontknow",
            sorted(
                (term for term in hard if forgotten[term.pk]),
                key=lambda term: -forgotten[term.pk],
            ),
            lambda term: _("%(count)s× forgotten") % {"count": forgotten[term.pk]},
        ),
        (
            "roller_coaster",
            "🐒",
            "think",
            sorted(
                (term for term in hard if switches[term.pk] >= SWITCHES),
                key=lambda term: -switches[term.pk],
            ),
            lambda term: _("%(count)s× switch know ↔ don't know") % {"count": switches[term.pk]},
        ),
        (
            "rush",
            "🐇",
            "dontknow",
            sorted(
                (term for term in hard if fast_wrong.get(term.pk, RUSH_MS) < RUSH_MS),
                key=lambda term: fast_wrong[term.pk],
            ),
            lambda term: (
                _("%(seconds)s s and don't know at all")
                % {"seconds": _decimal(fast_wrong[term.pk] / 1000)}
            ),
        ),
        (
            "again",
            "🐘",
            "dontknow",
            sorted(
                (term for term in hard if all_attempts[term.pk] >= REPEAT_ATTEMPTS),
                key=lambda term: -all_attempts[term.pk],
            ),
            lambda term: (
                _("don't know again · try no. %(count)s") % {"count": all_attempts[term.pk]}
            ),
        ),
        (
            "longest",
            "🦒",
            "partial",
            sorted(hard, key=lambda term: -len(term.main_foreign)),
            lambda term: _characters(len(term.main_foreign)),
        ),
        (
            "slow",
            "🐢",
            "ok",
            sorted(
                (term for term in hard if term.pk in think),
                key=lambda term: -_average(think[term.pk]),
            ),
            lambda term: (
                _("%(seconds)s s on average")
                % {"seconds": _decimal(_average(think[term.pk]) / 1000)}
            ),
        ),
        (
            "oldest",
            "🐌",
            "think",
            sorted(hard, key=lambda term: term.created_at),
            lambda term: _added_ago(term, now),
        ),
    ]
    by_kind = {candidate[0]: candidate for candidate in candidates}
    candidates = [by_kind[kind] for kind in kinds or STATS_FACTS]
    items = []
    used = set()
    for kind, emoji, tone, ordered, text in candidates:
        term = next((term for term in ordered if term.pk not in used), None)
        if kind == "mix_up":
            # Both words of the pair must be free
            term = next(
                (
                    term
                    for term in ordered
                    if term.pk not in used and partner[term.pk].pk not in used
                ),
                None,
            )
        if term is None:
            continue
        used.add(term.pk)
        foreign = term.main_foreign
        if kind == "mix_up":
            used.add(partner[term.pk].pk)
            foreign = f"{term.main_foreign} · {partner[term.pk].main_foreign}"
        # The card turns like in a test: every second one shows the native side first;
        # "one_way" shows the direction that is hard
        if kind == "one_way":
            native_first = one_direction(term)[0] == Direction.N2F
        else:
            native_first = len(items) % 2 == 1
        front, back = foreign, term.main_native
        if native_first:
            front, back = back, front
        items.append(
            {
                "kind": kind,
                "emoji": emoji,
                "title": str(FACT_TITLES[kind]),
                "tone": tone,
                "term": term,
                "word": foreign,
                "translation": term.main_native,
                "front": front,
                "back": back,
                "text": text(term),
            }
        )
    return {"items": items, "answered": True}


def _directions_text(term, bad_direction):
    """E.g. "EN → CS yes, CS → EN no" when native → foreign is the hard one."""
    foreign, native = term.foreign_language.code.upper(), term.native_language.code.upper()
    to_native, to_foreign = f"{foreign} → {native}", f"{native} → {foreign}"
    if bad_direction == Direction.N2F:
        good, bad = to_native, to_foreign
    else:
        good, bad = to_foreign, to_native
    return _("%(good)s yes, %(bad)s no") % {"good": good, "bad": bad}


def _added_ago(term, now):
    days = (_local_day(now) - _local_day(term.created_at)).days
    if days < 1:
        return _("added today")
    return ngettext("added %(count)s day ago", "added %(count)s days ago", days) % {"count": days}


def _average(values):
    return sum(values) / len(values)


def _characters(count):
    return ngettext("%(count)s character", "%(count)s characters", count) % {"count": count}


def _days(count):
    return ngettext("%(count)s day", "%(count)s days", count) % {"count": count}


def _decimal(value):
    """One decimal place with the decimal mark of the language (2,5 in Czech)."""
    return number_format(value, decimal_pos=1)
