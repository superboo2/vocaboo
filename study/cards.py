"""What one flash card shows (spec 6.4): question, answer, sentence and hints."""

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.db.models import Q

from vocabulary import sentences
from vocabulary.models import DeckTerm, Term, TermVariant

from .formatting import czech_plural
from .models import Direction
from .services import preview_intervals, session_deck_ids


@dataclass
class Card:
    state: object
    term: object
    direction: str
    # Variants on the question side and on the answer side, main variant first
    question: list
    answer: list
    # Sentence where the word was seen (with the word marked) and its source
    sentence: str = ""
    sentence_on_front: bool = False
    # Native → foreign: the sentence with a gap instead of the word, shown on the front
    cloze: str = ""
    source: str = ""
    # How many other decks of this test have the word too
    other_occurrences: int = 0
    # Short help on the front when the question alone is not clear
    front_hint: str = ""
    # Other meanings of the same foreign word: list of (hint, native variants)
    other_meanings: list = field(default_factory=list)
    # Other words with the same question text (N2F), e.g. "ahoj" is also "hello"
    also: list = field(default_factory=list)
    # (rating, interval) for every button
    preview: list = field(default_factory=list)

    @property
    def is_f2n(self):
        return self.direction == Direction.F2N


def build_card(session, state):
    term = state.term
    foreign = term.foreign_variants
    native = term.native_variants
    is_f2n = state.direction == Direction.F2N
    card = Card(
        state=state,
        term=term,
        direction=state.direction,
        question=foreign if is_f2n else native,
        answer=native if is_f2n else foreign,
        preview=preview_intervals(state),
    )

    _add_sentence(card, session, foreign)
    if is_f2n:
        _add_other_meanings(card)
    else:
        _add_same_translation(card, native)
    return card


def _add_sentence(card, session, foreign):
    deck_terms = DeckTerm.objects.filter(term=card.term).order_by("added_at", "pk")
    if not session.terms.exists():
        deck_terms = deck_terms.filter(deck_id__in=session_deck_ids(session))
    deck_terms = list(deck_terms)
    card.other_occurrences = max(0, len(deck_terms) - 1)

    with_sentence = [item for item in deck_terms if item.context_sentence]
    if not with_sentence:
        return
    # A different sentence each time the card comes back
    chosen = with_sentence[card.state.reviews_count % len(with_sentence)]
    card.sentence = sentences.highlight(chosen.context_sentence, foreign)
    card.source = chosen.context_source
    if card.is_f2n:
        # The sentence shows which meaning is meant (palm: hand or tree)
        card.sentence_on_front = True
    elif sentences.has_word(chosen.context_sentence, foreign):
        # The full sentence would give the answer away, so the front gets a gap.
        # When the word was not found (other form, no braces), the sentence stays on the back.
        card.cloze = sentences.cloze(chosen.context_sentence, foreign)


def _add_other_meanings(card):
    term = card.term
    others = list(
        Term.objects.filter(
            owner_id=term.owner_id,
            foreign_language_id=term.foreign_language_id,
            native_language_id=term.native_language_id,
            main_foreign__iexact=term.main_foreign,
        )
        .exclude(pk=term.pk)
        .prefetch_related("variants")
        .order_by("meaning_hint")
    )
    if not others:
        return
    card.other_meanings = [(other.meaning_hint, other.native_variants) for other in others]
    if not card.sentence_on_front:
        # Without a sentence the question "palm" has more right answers
        count = len(others) + 1
        meanings = czech_plural(count, "význam", "významy", "významů")
        card.front_hint = f"{term.meaning_hint} · {count} {meanings}"


def _add_same_translation(card, native):
    term = card.term
    same_text = reduce(
        or_,
        (Q(variants__side=TermVariant.Side.NATIVE, variants__text__iexact=text) for text in native),
    )
    others = (
        Term.objects.filter(
            same_text,
            owner_id=term.owner_id,
            foreign_language_id=term.foreign_language_id,
            native_language_id=term.native_language_id,
        )
        .exclude(pk=term.pk)
        .distinct()
        .order_by("main_foreign")
    )
    card.also = [other.main_foreign for other in others]
    if card.also and term.meaning_hint:
        card.front_hint = term.meaning_hint
