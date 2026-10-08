"""Business logic for study: intervals (spec 6.3), choosing cards and saving answers (6.2)."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from vocabulary.models import DeckTerm
from vocabulary.services import get_descendant_ids

from .models import (
    Direction,
    Result,
    ReviewLog,
    ReviewState,
    StudyDirection,
    StudyScope,
    StudySession,
)
from .ratings import RATINGS, get_rating

ONE_DAY = timedelta(days=1)


def round_interval(interval):
    """Round intervals of one day or longer to whole days (half goes up).

    Then a word comes back at the same time of day and the numbers are easy to read,
    e.g. 3 days × 2.5 = 7.5 days becomes 8 days.
    """
    if interval < ONE_DAY:
        return interval
    days = int(interval / ONE_DAY + 0.5)
    return timedelta(days=days)


def next_interval(rating, last_interval):
    """Interval after the rating, based on the interval used last time."""
    if rating.multiplier is not None and last_interval is not None:
        interval = last_interval * rating.multiplier
    else:
        interval = rating.min_interval
    interval = max(rating.min_interval, min(interval, rating.max_interval))
    return round_interval(interval)


def preview_intervals(state):
    """Interval of every button for this card, to show it under the emoji."""
    return [(rating, next_interval(rating, state.last_interval)) for rating in RATINGS]


def apply_rating(state, rating_key, now=None):
    """Change the review state after the user rated the card. Returns the interval.

    The state is only changed, not saved; the caller saves it together with the log.
    """
    rating = get_rating(rating_key)
    now = now or timezone.now()
    interval = next_interval(rating, state.last_interval)

    state.due_at = now + interval
    state.last_reviewed_at = now
    state.last_rating = rating.key
    # After "partial" or "wrong" this is their short interval, so growing starts again
    state.last_interval = interval
    state.reviews_count += 1
    if rating.result == Result.CORRECT:
        state.correct_streak += 1
    else:
        state.correct_streak = 0
    if rating.result == Result.WRONG:
        state.lapses += 1
    return interval


# Sessions

# Longer times mean the user left; they are not saved
MAX_ANSWER_MS = 5 * 60 * 1000

# How many next cards are looked at to keep the same word from coming twice in a row
CANDIDATE_WINDOW = 20


def start_session(
    user,
    decks=(),
    *,
    direction=StudyDirection.MIXED,
    scope=StudyScope.DUE,
    max_cards=None,
    terms=(),
):
    """Start a test from the chosen decks (their child decks are included).

    With terms the test has only these words, e.g. "practise the wrong ones again".
    """
    decks = list(decks)
    terms = list(terms)
    if not decks and not terms:
        raise ValidationError(_("Vyber aspoň jeden slovník."))
    if any(deck.owner_id != user.pk for deck in decks):
        raise ValidationError(_("Slovník patří jinému uživateli."))
    if any(term.owner_id != user.pk for term in terms):
        raise ValidationError(_("Slovíčko patří jinému uživateli."))
    if max_cards is not None and max_cards < 1:
        raise ValidationError(_("Počet karet musí být aspoň 1."))
    with transaction.atomic():
        session = StudySession.objects.create(
            user=user, direction=direction, scope=scope, max_cards=max_cards
        )
        session.decks.set(decks)
        session.terms.set(terms)
    return session


def session_deck_ids(session):
    """Ids of the chosen decks and all their child decks."""
    ids = set()
    for deck in session.decks.all():
        ids.update(get_descendant_ids(deck))
    return ids


def session_term_ids(session):
    """Query with the ids of words in the session; a word in more decks is there once."""
    if session.terms.exists():
        return session.terms.through.objects.filter(studysession=session).values("term_id")
    return (
        DeckTerm.objects.filter(deck_id__in=session_deck_ids(session)).values("term_id").distinct()
    )


def session_cards(session, now=None):
    """Review states that can still come in this session, the first one goes first."""
    now = now or timezone.now()
    cards = ReviewState.objects.filter(
        term_id__in=session_term_ids(session),
        direction__in=session.directions,
    )
    if session.scope == StudyScope.DUE:
        # Cards that are due, and new cards that were never reviewed
        cards = cards.filter(Q(due_at__lte=now) | Q(due_at__isnull=True))
    else:
        # Every card once; an answered card comes again only when it is due
        cards = cards.exclude(last_reviewed_at__gte=session.started_at, due_at__gt=now)
    # Due cards from the oldest, then new cards in the order they were added
    return cards.order_by(F("due_at").asc(nulls_last=True), "term__created_at", "term_id", "pk")


def next_card(session, now=None):
    """The next card to show, or None when the session is over."""
    if session.finished_at is not None:
        return None
    if session.max_cards is not None and session.answered >= session.max_cards:
        return None
    candidates = list(
        session_cards(session, now)
        .select_related("term")
        .prefetch_related("term__variants")[:CANDIDATE_WINDOW]
    )
    if not candidates:
        return None

    last = session.logs.select_related("term").order_by("-reviewed_at", "-pk").first()
    if last is None:
        return candidates[0]
    for card in candidates:
        # Not the same word again (other direction), and not another meaning of it (palm/palm)
        if card.term_id == last.term_id:
            continue
        if card.term.main_foreign.lower() == last.term.main_foreign.lower():
            continue
        return card
    return candidates[0]


def finish_session(session, now=None):
    if session.finished_at is None:
        session.finished_at = now or timezone.now()
        session.save(update_fields=["finished_at"])
    return session


def record_answer(session, state, rating_key, *, think_ms=None, decide_ms=None, now=None):
    """Save one answer: new review state, a line in the history and session counters."""
    rating = get_rating(rating_key)
    now = now or timezone.now()
    with transaction.atomic():
        # Lock the row, so two devices cannot change the same card at the same time
        state = ReviewState.objects.select_for_update().get(pk=state.pk)
        if (
            state.direction not in session.directions
            or not session_term_ids(session).filter(term_id=state.term_id).exists()
        ):
            raise ValidationError(_("Tato kartička do testu nepatří."))

        interval = apply_rating(state, rating.key, now=now)
        state.save()
        log = ReviewLog.objects.create(
            user_id=session.user_id,
            term_id=state.term_id,
            session=session,
            direction=state.direction,
            rating=rating.key,
            rating_label=str(rating.label),
            result=rating.result,
            chosen_interval=interval,
            think_ms=_clean_ms(think_ms),
            decide_ms=_clean_ms(decide_ms),
            reviewed_at=now,
        )
        is_correct = 1 if rating.result == Result.CORRECT else 0
        StudySession.objects.filter(pk=session.pk).update(
            answered=F("answered") + 1, correct=F("correct") + is_correct
        )
    session.refresh_from_db(fields=["answered", "correct"])
    return log


def session_summary(session):
    """Numbers for the end of a test (spec 6.7)."""
    logs = list(session.logs.select_related("term").order_by("reviewed_at", "pk"))
    counts = {rating.key: 0 for rating in RATINGS}
    problems = {}
    for log in logs:
        counts[log.rating] = counts.get(log.rating, 0) + 1
        if log.result != Result.CORRECT:
            problems.setdefault(log.term_id, log.term)
    return {
        "answered": len(logs),
        "counts": [(rating, counts[rating.key]) for rating in RATINGS],
        # Words rated "partial" or "don't know", each once, in the order they came
        "problem_terms": list(problems.values()),
    }


def _clean_ms(value):
    """Time from the browser: a whole number of milliseconds, or None when it makes no sense."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if value < 0 or value > MAX_ANSWER_MS:
        return None
    return value


# Numbers for the dashboard and the word page


def annotate_deck_counts(roots, user, now=None):
    """Add word counts to every deck of the tree from vocabulary.services.load_tree.

    Counts include child decks and every word is counted once, even when it is in more decks:
    deck.word_count (all words), deck.due_count (a direction is due now),
    deck.new_count (never reviewed). Returns the counts for all decks together.
    """
    now = now or timezone.now()
    words_by_deck = {}
    for deck_id, term_id in DeckTerm.objects.filter(deck__owner=user).values_list(
        "deck_id", "term_id"
    ):
        words_by_deck.setdefault(deck_id, set()).add(term_id)
    states = ReviewState.objects.filter(term__owner=user)
    due = set(states.filter(due_at__lte=now).values_list("term_id", flat=True))
    reviewed = set(states.filter(due_at__isnull=False).values_list("term_id", flat=True))

    def count(deck):
        words = set(words_by_deck.get(deck.pk, set()))
        for child in deck.tree_children:
            words |= count(child)
        deck.word_count = len(words)
        deck.due_count = len(words & due)
        deck.new_count = len(words - reviewed)
        return words

    all_words = set()
    for root in roots:
        all_words |= count(root)
    return {
        "words": len(all_words),
        "due": len(all_words & due),
        "new": len(all_words - reviewed),
    }


def term_history(term, limit=100):
    """Review state, rating counts and answers of one word, for each direction (spec 7.1)."""
    states = {state.direction: state for state in term.review_states.all()}
    logs = list(term.review_logs.order_by("-reviewed_at", "-pk")[:limit])
    counts = {}
    for log in term.review_logs.values_list("direction", "rating"):
        direction, rating = log
        counts.setdefault(direction, {}).setdefault(rating, 0)
        counts[direction][rating] += 1

    directions = []
    for direction in Direction.values:
        state = states.get(direction)
        rating_counts = counts.get(direction, {})
        directions.append(
            {
                "direction": direction,
                "label": Direction(direction).label,
                "state": state,
                "total": sum(rating_counts.values()),
                "counts": [(rating, rating_counts.get(rating.key, 0)) for rating in RATINGS],
            }
        )
    return {"directions": directions, "logs": logs}
