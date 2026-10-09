"""What one flash card shows (spec 6.4): question, answer, sentence and hints."""

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.db.models import Q

from dictionary.providers import other_meanings
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
    # Sentence where the word was seen (with the word marked)
    sentence: str = ""
    sentence_on_front: bool = False
    # Native → foreign: the sentence with a gap instead of the word, shown on the front
    cloze: str = ""
    # Short help on the front when the question alone is not clear
    front_hint: str = ""
    # The user's own words with the same foreign text: list of native variants per word
    own_meanings: list = field(default_factory=list)
    # Other meanings of the foreign word from dictionaries, only the first variant of each,
    # and the names of the dictionaries. The browser shows as many as fit on one line and
    # "+N" for the rest (study.js).
    dictionary_meanings: list = field(default_factory=list)
    dictionary_sources: list = field(default_factory=list)
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
    _add_other_meanings(card, session.user)
    if not is_f2n:
        # The hint "2 významy" is only for the foreign word on the front
        card.front_hint = ""
        _add_same_translation(card, native)
    return card


def _add_sentence(card, session, foreign):
    deck_terms = DeckTerm.objects.filter(term=card.term).order_by("added_at", "pk")
    if not session.terms.exists():
        deck_terms = deck_terms.filter(deck_id__in=session_deck_ids(session))

    with_sentence = [item for item in deck_terms if item.context_sentence]
    if not with_sentence:
        return
    # A different sentence each time the card comes back
    chosen = with_sentence[card.state.reviews_count % len(with_sentence)]
    card.sentence = sentences.highlight(chosen.context_sentence, foreign)
    if card.is_f2n:
        # The sentence shows which meaning is meant (palm: hand or tree)
        card.sentence_on_front = True
    elif sentences.has_word(chosen.context_sentence, foreign):
        # The full sentence would give the answer away, so the front gets a gap.
        # When the word was not found (other form, no braces), the sentence stays on the back.
        card.cloze = sentences.cloze(chosen.context_sentence, foreign)


def _add_other_meanings(card, user):
    meanings = other_meanings(card.term, include_dictionary=user.show_other_meanings)
    own = [meaning for meaning in meanings if meaning["own"]]
    card.own_meanings = [meaning["variants"] for meaning in own]

    # Only the first variant of each meaning, so meanings can be split by dots:
    # "moment · přídavek · druhý" instead of "moment; okamžik · přídavek; nášup · druhý".
    # Meanings of all dictionaries go into one line, the same word only once.
    for meaning in meanings:
        if meaning["own"]:
            continue
        if meaning["variants"][0] not in card.dictionary_meanings:
            card.dictionary_meanings.append(meaning["variants"][0])
        if meaning["source"] and meaning["source"] not in card.dictionary_sources:
            card.dictionary_sources.append(meaning["source"])

    if own and not card.sentence_on_front:
        # Without a sentence the question "palm" has more right answers among the user's words
        count = len(own) + 1
        card.front_hint = f"{count} {czech_plural(count, 'význam', 'významy', 'významů')}"


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
