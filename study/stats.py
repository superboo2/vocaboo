"""Statistics page: totals, words over time, the last tests and the words that are hard.

Everything is counted from the words (Term.created_at), the answers (ReviewLog) and the review
states, nothing extra is stored. The user has hundreds or thousands of rows at most, so the
numbers are counted in Python from simple queries.
"""

from collections import Counter
from datetime import timedelta

from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.utils import timezone

from vocabulary.models import DeckTerm, Term
from vocabulary.services import deck_names, deck_path

from .formatting import czech_plural
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

# A word counts as known when foreign → native was right this many times in a row
# (its interval is then a week or more)
KNOWN_STREAK = 2
# Weeks in the chart
CHART_WEEKS = 12

# The table "Poslední testy": how many tests, and the days of the line above it
RECENT_TESTS = 10
TESTS_DAYS = 14
WEEKDAY_SHORT = ["po", "út", "st", "čt", "pá", "so", "ne"]

# Days in the bar chart of the dashboard (today is the last one)
WEEK_DAYS = 7

# Periods of the fun facts: key in the URL (?period=30) → (days or None for all, name)
PERIODS = {"7": (7, "7 dní"), "30": (30, "30 dní"), "all": (None, "Vše")}
DEFAULT_PERIOD = "7"
# "Horská dráha" needs this many changes between right and wrong, "Moc rychle" a "vůbec
# nevím" faster than this (ms)
SWITCHES = 3
RUSH_MS = 3000
# The dashboard: only today, and these kinds of cards in this order
TODAY = "today"
TODAY_FACTS = ["Nejdéle přemýšlíš u", "Jen jedním směrem", "Pořád dokola"]
# The statistics page (all kinds but the dashboard's "Pořád dokola", in this order)
STATS_FACTS = [
    "Největší nepřítel",
    "Pleteš si",
    "Jen jedním směrem",
    "Zapomínáš",
    "Horská dráha",
    "Moc rychle",
    "Nejdelší, co ti nejde",
    "Nejdéle přemýšlíš u",
    "Nejdéle se učíš",
]
# "Pořád dokola" shows a word only after this many attempts in the whole history
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
    """Words the user knows: foreign → native right KNOWN_STREAK times in a row ("umíš")."""
    return ReviewState.objects.filter(
        term__owner=user, direction=Direction.F2N, correct_streak__gte=KNOWN_STREAK
    ).count()


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
        summary = (
            f"Za {TESTS_DAYS} dní {len(recent)} "
            f"{czech_plural(len(recent), 'test', 'testy', 'testů')} · průměrně {average} "
            f"{czech_plural(average, 'slovíčko', 'slovíčka', 'slovíček')}"
        )
    return {"rows": rows, "summary": summary}


def today_overview(user, now=None):
    """Today on the dashboard, only good news of the tests, each with its last WEEK_DAYS days
    for a small bar chart (today is the last day), and the words added today:

    - added: words added (still in a deck), only today,
    - first right: words right (😎 or 🤔, any direction) for the first time ever,
    - learned: words for the first time right KNOWN_STREAK times in a row foreign → native
      (the same "umíš" as on the statistics page),
    - tested: different words in the tests (both directions count once),
    - minutes: the length of the tests (to the last answer), by the day the test began.
    """
    now = now or timezone.now()
    today = _local_day(now)
    days = [today - timedelta(days=back) for back in range(WEEK_DAYS - 1, -1, -1)]
    midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight - timedelta(days=WEEK_DAYS - 1)

    added = Counter(
        _local_day(created)
        for created in Term.objects.filter(
            owner=user, created_at__gte=since, deck_terms__isnull=False
        )
        .distinct()
        .values_list("created_at", flat=True)
    )
    first_right = Counter(
        _local_day(first)
        for first in ReviewLog.objects.filter(user=user, result=Result.CORRECT)
        .values("term_id")
        .annotate(first=Min("reviewed_at"))
        .filter(first__gte=since)
        .values_list("first", flat=True)
    )
    learned = Counter()
    in_a_row = Counter()
    known = set()
    for term_id, result, reviewed_at in (
        ReviewLog.objects.filter(user=user, direction=Direction.F2N)
        .order_by("reviewed_at", "pk")
        .values_list("term_id", "result", "reviewed_at")
    ):
        in_a_row[term_id] = in_a_row[term_id] + 1 if result == Result.CORRECT else 0
        if in_a_row[term_id] == KNOWN_STREAK and term_id not in known:
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

    def word(count):
        return czech_plural(count, "slovíčko", "slovíčka", "slovíček")

    def metric(key, icon, values, label, help_text, unit=""):
        top = max(values[day] for day in days) or 1
        return {
            "key": key,
            "icon": icon,
            "value": f"{values[today]}{unit}",
            "label": label,
            # The tooltip of the number: what exactly is counted
            "help": help_text,
            "bars": [
                {
                    "value": f"{values[day]}{unit}",
                    "height": f"{100 * values[day] / top:.0f}",
                    "label": "dnes" if day == today else WEEKDAY_SHORT[day.weekday()],
                    "title": f"{day.day}. {day.month}.",
                    "today": day == today,
                }
                for day in days
            ],
        }

    # Words added today are not one of the numbers (they are about the decks, the numbers are
    # about the tests); the dashboard shows them next to all the words
    return {
        "added_today": added[today],
        "metrics": [
            metric(
                "tested",
                "📚",
                tested,
                f"{word(tested[today])} v testech",
                "Různá slovíčka, která byla dnes v testech. Slovíčko v obou směrech "
                "se počítá jednou.",
            ),
            metric(
                "first",
                "🎯",
                first_right,
                "poprvé správně",
                "Slovíčka, u kterých byla dnes poprvé v historii odpověď 😎 nebo 🤔, "
                "v kterémkoli směru. Každé slovíčko se počítá jednou.",
            ),
            metric(
                "learned",
                "🎓",
                learned,
                f"{word(learned[today])} naučeno",
                "Slovíčka, která dnes poprvé splnila „umíš“: ve směru cizí → rodný "
                "dvakrát po sobě správně. Druhá správná odpověď přijde až po intervalu, "
                "u nových slovíček tedy nejdřív za pár dní.",
            ),
            metric(
                "minutes",
                "⏱️",
                minutes,
                "čas v testech",
                "Jak dlouho dnes trvaly testy (od začátku testu do poslední odpovědi).",
                " min",
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
    foreign, native = "cizí", "rodný"
    if decks:
        foreign = decks[0].foreign_language.code.upper()
        native = decks[0].native_language.code.upper()
    direction = {
        StudyDirection.F2N: f"{foreign} → {native}",
        StudyDirection.N2F: f"{native} → {foreign}",
    }.get(session.direction, f"{foreign} ↔ {native}")
    scope = "všechna" if session.scope == StudyScope.ALL else "opak. + nová"
    if session.retry:
        scope = "chybné znovu"
    finished = session.finished_at is not None or (
        session.max_cards is not None and session.cards >= session.max_cards
    )
    minutes = round((session.last_answer - session.started_at).total_seconds() / 60)
    ratings = [{"rating": rating, "count": counts[session.pk, rating.key]} for rating in RATINGS]
    percent = round(100 * session.correct_cards / session.cards)
    return {
        "session": session,
        "when": f"{WEEKDAY_SHORT[started.weekday()]} {started.day}. {started.month}.",
        "time": f"{started:%H:%M}",
        "paths": [deck_path(deck.pk, names) for deck in decks],
        "direction": direction,
        "scope": scope,
        "limit": f"max {session.max_cards}" if session.max_cards else "",
        "cards": session.cards,
        "ratings": ratings,
        "percent": percent,
        "finished": finished,
        "time_spent": _minutes(minutes),
    }


def _minutes(minutes):
    if minutes < 1:
        return "< 1 min"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60} min"


def hard_words(user, now=None):
    """The cards "Co ti dnes nejde" for the dashboard: only today's answers, 4 kinds."""
    now = now or timezone.now()
    return _facts(user, _logs(user), now, TODAY, kinds=TODAY_FACTS)["items"]


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


def _weeks(today, count):
    first = _week_start(today) - timedelta(weeks=count - 1)
    return [first + timedelta(weeks=index) for index in range(count)]


def _words_chart(terms, today):
    """All words week by week (the line goes up as words are added)."""
    weeks = _weeks(today, CHART_WEEKS)
    added = Counter(_week_start(_local_day(created)) for created, _word, _pk in terms)
    running = sum(count for week, count in added.items() if week < weeks[0])
    totals = []
    for week in weeks:
        running += added.get(week, 0)
        totals.append(running)
    return _line_chart(weeks, totals)


def _nice_top(value):
    """A round top of the y axis: 7 -> 8, 63 -> 80, 230 -> 250."""
    if value <= 4:
        return 4
    step = 10 ** (len(str(int(value))) - 1)
    for factor in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= factor * step:
            return int(factor * step)
    return int(10 * step)


def _line_chart(weeks, values):
    """A simple line chart: points of the weeks and the y axis with 5 round values.

    Positions are percents of the drawing area (0 = left / top): the SVG draws the line in a
    0–100 box stretched to the page, the dots and labels are HTML placed by the same percents.
    A week without a value (None) breaks the line.
    """
    top = _nice_top(max((value for value in values if value is not None), default=0))
    last = len(weeks) - 1
    points = []
    segments = []
    segment = []
    for index, (week, value) in enumerate(zip(weeks, values, strict=True)):
        if value is None:
            if segment:
                segments.append(segment)
            segment = []
            continue
        left = 100 * index / last
        y = 100 - 100 * value / top
        points.append(
            {
                "left": f"{left:.2f}",
                "top": f"{y:.2f}",
                "title": f"{week.day}. {week.month}.: {value}",
            }
        )
        segment.append(f"{left:.2f},{y:.2f}")
    if segment:
        segments.append(segment)
    ticks = [{"label": str(top * part // 4), "top": f"{100 - 25 * part:.0f}"} for part in range(5)]
    # A date under every third week, the last week always
    labels = [
        {"label": f"{week.day}. {week.month}.", "left": f"{100 * index / last:.2f}"}
        for index, week in enumerate(weeks)
        if (last - index) % 3 == 0
    ]
    return {
        "points": points,
        "segments": [" ".join(segment) for segment in segments],
        "ticks": ticks,
        "labels": labels,
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
        "current_text": f"{current} {czech_plural(current, 'den', 'dny', 'dní')}",
        "longest_text": f"{longest} {czech_plural(longest, 'den', 'dny', 'dní')}",
    }


def _facts(user, logs, now, period, kinds=None):
    """The "nej" words that are hard: each one shows a word with its translation.

    A word is hard when in the period it had an answer "vůbec nevím" or "napůl" and it is
    still not known (some direction has fewer than KNOWN_STREAK right answers in a row).
    One word is shown only once, the next fact takes the next word in its order.
    """
    if period == TODAY:
        since = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
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

    # Attempts of a word in the whole history (for "Pořád dokola")
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
        tries = czech_plural(count, "pokusu", "pokusů", "pokusů")
        return f"{wrong[term.pk]}× vůbec nevím z {count} {tries}"

    hard = list(terms.values())
    # (animal, what it is, colour of the stripe, words in order, why)
    candidates = [
        (
            "🦈",
            "Největší nepřítel",
            "dontknow",
            sorted(
                (term for term in hard if wrong[term.pk]),
                key=lambda term: (-wrong[term.pk], -attempts[term.pk]),
            ),
            enemy_text,
        ),
        (
            "🦎",
            "Pleteš si",
            "partial",
            sorted(
                (term for term in hard if term.pk in partner),
                key=lambda term: -(wrong[term.pk] + wrong[partner[term.pk].pk]),
            ),
            lambda term: "stejný překlad, pořád se pletou",
        ),
        (
            "🦀",
            "Jen jedním směrem",
            "think",
            [term for term in hard if one_direction(term)],
            lambda term: _directions_text(term, one_direction(term)[0]),
        ),
        (
            "🐿️",
            "Zapomínáš",
            "dontknow",
            sorted(
                (term for term in hard if forgotten[term.pk]),
                key=lambda term: -forgotten[term.pk],
            ),
            lambda term: f"{forgotten[term.pk]}× zapomenuto",
        ),
        (
            "🐒",
            "Horská dráha",
            "think",
            sorted(
                (term for term in hard if switches[term.pk] >= SWITCHES),
                key=lambda term: -switches[term.pk],
            ),
            lambda term: f"{switches[term.pk]}× změna vím ↔ nevím",
        ),
        (
            "🐇",
            "Moc rychle",
            "dontknow",
            sorted(
                (term for term in hard if fast_wrong.get(term.pk, RUSH_MS) < RUSH_MS),
                key=lambda term: fast_wrong[term.pk],
            ),
            lambda term: f"za {fast_wrong[term.pk] / 1000:.1f} s a vůbec nevím".replace(".", ","),
        ),
        (
            "🐘",
            "Pořád dokola",
            "dontknow",
            sorted(
                (term for term in hard if all_attempts[term.pk] >= REPEAT_ATTEMPTS),
                key=lambda term: -all_attempts[term.pk],
            ),
            lambda term: f"zase nevím · už {all_attempts[term.pk]}. pokus",
        ),
        (
            "🦒",
            "Nejdelší, co ti nejde",
            "partial",
            sorted(hard, key=lambda term: -len(term.main_foreign)),
            lambda term: _characters(len(term.main_foreign)),
        ),
        (
            "🐢",
            "Nejdéle přemýšlíš u",
            "ok",
            sorted(
                (term for term in hard if term.pk in think),
                key=lambda term: -_average(think[term.pk]),
            ),
            lambda term: f"průměrně {_average(think[term.pk]) / 1000:.1f} s".replace(".", ","),
        ),
        (
            "🐌",
            "Nejdéle se učíš",
            "think",
            sorted(hard, key=lambda term: term.created_at),
            lambda term: _added_ago(term, now),
        ),
    ]
    by_title = {candidate[1]: candidate for candidate in candidates}
    candidates = [by_title[title] for title in kinds or STATS_FACTS]
    items = []
    used = set()
    for emoji, title, tone, ordered, text in candidates:
        term = next((term for term in ordered if term.pk not in used), None)
        if title == "Pleteš si":
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
        if title == "Pleteš si":
            used.add(partner[term.pk].pk)
            foreign = f"{term.main_foreign} · {partner[term.pk].main_foreign}"
        # The card turns like in a test: every second one shows the native side first;
        # "Jen jedním směrem" shows the direction that is hard
        if title == "Jen jedním směrem":
            native_first = one_direction(term)[0] == Direction.N2F
        else:
            native_first = len(items) % 2 == 1
        front, back = foreign, term.main_native
        if native_first:
            front, back = back, front
        items.append(
            {
                "emoji": emoji,
                "title": title,
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
    """E.g. "EN → CS ano, CS → EN ne" when native → foreign is the hard one."""
    foreign, native = term.foreign_language.code.upper(), term.native_language.code.upper()
    to_native, to_foreign = f"{foreign} → {native}", f"{native} → {foreign}"
    if bad_direction == Direction.N2F:
        return f"{to_native} ano, {to_foreign} ne"
    return f"{to_foreign} ano, {to_native} ne"


def _added_ago(term, now):
    days = (_local_day(now) - _local_day(term.created_at)).days
    if days < 1:
        return "přidáno dnes"
    return f"přidáno před {days} {czech_plural(days, 'dnem', 'dny', 'dny')}"


def _average(values):
    return sum(values) / len(values)


def _characters(count):
    return f"{count} {czech_plural(count, 'znak', 'znaky', 'znaků')}"
