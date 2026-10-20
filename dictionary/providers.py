"""Translation suggestions shown while a word is typed, other meanings and pronunciation.

Every source is a provider with the same small interface, so sources can be added or
changed later without touching the rest of the app. The order of the sources is the
setting SUGGESTION_PROVIDERS (and PRONUNCIATION_PROVIDERS); the first source that knows the
word wins. Today there is one source: the dictionary of the app (dictionary.models: words of
the foreign language point to concepts, the concepts have the texts of the native language).
"""

from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import pgettext_lazy

from vocabulary.services import parse_variants

from .models import ConceptText, ConceptTextForm, LexiconWord, PartOfSpeech, WordSense

# Most suggestions shown for one word
LIMIT = 12

# Short names of parts of speech for the small suggestion buttons
SHORT_POS = {
    "noun": pgettext_lazy("part of speech", "n."),
    "verb": pgettext_lazy("part of speech", "v."),
    "adjective": pgettext_lazy("part of speech", "adj."),
    "adverb": pgettext_lazy("part of speech", "adv."),
    "pronoun": pgettext_lazy("part of speech", "pron."),
    "determiner": pgettext_lazy("part of speech", "det."),
    "preposition": pgettext_lazy("part of speech", "prep."),
    "conjunction": pgettext_lazy("part of speech", "conj."),
    "interjection": pgettext_lazy("part of speech", "interj."),
    "numeral": pgettext_lazy("part of speech", "num."),
    "phrasal_verb": pgettext_lazy("part of speech", "phr. v."),
    "phrase": pgettext_lazy("part of speech", "phrase"),
}


@dataclass
class Suggestion:
    # Text for the translation field, variants separated by "; " (e.g. "dárek; dar")
    translation: str
    # Code of the part of speech, e.g. "noun"
    part_of_speech: str = ""
    # Short hint that tells the meanings apart, e.g. "váha"
    note: str = ""
    # Example sentences: list of dicts {"text", "translation"}; the word is in braces
    examples: list = field(default_factory=list)

    @property
    def short_pos(self):
        # str(): the text in the active language (it may end up in JSON)
        return str(SHORT_POS.get(self.part_of_speech, self.part_of_speech))

    @property
    def pos_label(self):
        return PartOfSpeech(self.part_of_speech).label if self.part_of_speech else ""


@dataclass
class SuggestionResult:
    suggestions: list


@dataclass
class Pronunciation:
    # Pronunciation in IPA without brackets, e.g. "pɑːm"
    ipa: str = ""


class Provider:
    name = ""

    def suggest(self, word, foreign_code, native_code):
        """Return a SuggestionResult, or None when the source does not know the word."""
        return None

    def pronounce(self, word, foreign_code):
        """Return a Pronunciation, or None when the source does not know the word."""
        return None

    def example(self, word, foreign_code, native_code, translations):
        """Return {"text", "translation"} for the meaning with one of the translations
        (a set of lower case texts), or None."""
        return None


@dataclass
class Meaning:
    """One meaning of a typed word for a language pair (a word sense and its concept)."""

    translation: str
    part_of_speech: str
    note: str
    sentence: str
    sentence_native: str


# The concepts are built from English: for a concept found only by its text (a language without
# words, e.g. Czech), the English word of the concept gives the part of speech and the order
DEFINING_LANGUAGE = "en"


def _senses(word, foreign_code, native_code):
    """Meanings of the typed word for the pair, the most common first.

    The word is looked up twice: as a word of the foreign language (with its other forms, e.g.
    "palms" for "palm"; languages that have words, today English), and in the texts of the
    concepts in the foreign language ("kočka" in "kočka; kocour"), so every pair works as soon
    as both languages have texts. The concepts give the translation, the note and the sentence
    in the native language; a concept without a native text has no translation yet.
    """
    typed = word.lower()
    found = [
        (sense.concept_id, sense.word.part_of_speech)
        for sense in WordSense.objects.filter(word__forms__text=typed, word__language=foreign_code)
        .select_related("word")
        .order_by("word__band", "word_id", "position")
    ]
    seen = {concept_id for concept_id, _pos in found}
    by_text = set(
        ConceptTextForm.objects.filter(form=typed, text__language=foreign_code)
        .exclude(text__concept_id__in=seen)
        .values_list("text__concept_id", flat=True)
    )
    if by_text:
        # Ordered by the English word of the concept, the same order as from English
        ordered = (
            WordSense.objects.filter(concept_id__in=by_text, word__language=DEFINING_LANGUAGE)
            .select_related("word")
            .order_by("word__band", "word_id", "position")
        )
        for sense in ordered:
            if sense.concept_id not in seen:
                seen.add(sense.concept_id)
                found.append((sense.concept_id, sense.word.part_of_speech))
        found += [(concept_id, "") for concept_id in sorted(by_text - seen)]

    texts = {
        (text.concept_id, text.language): text
        for text in ConceptText.objects.filter(
            concept_id__in=[concept_id for concept_id, _pos in found],
            language__in=[foreign_code, native_code],
        )
    }
    meanings = []
    for concept_id, part_of_speech in found:
        native = texts.get((concept_id, native_code))
        if native is None:
            continue
        foreign = texts.get((concept_id, foreign_code))
        meanings.append(
            Meaning(
                translation=native.words,
                part_of_speech=part_of_speech,
                note=native.note,
                sentence=foreign.sentence if foreign else "",
                sentence_native=native.sentence,
            )
        )
    return meanings


class LexiconProvider(Provider):
    """The dictionary of the app, imported by the command import_lexicon."""

    name = "lexicon"

    def suggest(self, word, foreign_code, native_code):
        suggestions = []
        seen = set()
        for sense in _senses(word, foreign_code, native_code):
            if sense.translation.lower() in seen:
                continue
            seen.add(sense.translation.lower())
            suggestions.append(
                Suggestion(
                    translation=sense.translation,
                    part_of_speech=sense.part_of_speech,
                    note=sense.note,
                    examples=[{"text": sense.sentence, "translation": sense.sentence_native}],
                )
            )
            if len(suggestions) == LIMIT:
                break
        if not suggestions:
            return None
        return SuggestionResult(suggestions=suggestions)

    def example(self, word, foreign_code, native_code, translations):
        """The sentence of the meaning that has one of the translations, or None.

        Only the right meaning: for palm → dlaň not the sentence about the palm tree.
        """
        for sense in _senses(word, foreign_code, native_code):
            variants = {text.lower() for text in parse_variants(sense.translation)}
            if variants & translations:
                return {"text": sense.sentence, "translation": sense.sentence_native}
        return None

    def pronounce(self, word, foreign_code):
        ipa = (
            LexiconWord.objects.filter(forms__text=word.lower(), language=foreign_code)
            .exclude(ipa="")
            .order_by("band", "pk")
            .values_list("ipa", flat=True)
            .first()
        )
        return Pronunciation(ipa=ipa) if ipa else None


PROVIDERS = {provider.name: provider for provider in [LexiconProvider()]}


def get_suggestions(word, foreign_code, native_code):
    """Suggestions for the first variant of the typed word, from the first source that knows it."""
    variants = parse_variants(word)
    if not variants:
        return None
    for name in settings.SUGGESTION_PROVIDERS:
        provider = PROVIDERS.get(name)
        if provider is None:
            continue
        result = provider.suggest(variants[0], foreign_code, native_code)
        if result is not None:
            return result
    return None


def get_pronunciation(word, foreign_code, with_ipa=True):
    """Pronunciation (IPA) of the first variant of the word, or None.

    The sound itself is made by the voice of the browser (static/js/app.js). With
    with_ipa=False the user does not want to see the IPA, so there is nothing to show.
    """
    variants = parse_variants(word)
    if not variants or not with_ipa:
        return None
    for name in settings.PRONUNCIATION_PROVIDERS:
        provider = PROVIDERS.get(name)
        if provider is None:
            continue
        result = provider.pronounce(variants[0], foreign_code)
        if result is not None:
            return result
    return None


def get_example_sentence(term):
    """An example sentence from the dictionary for the meaning of the user's word, or None.

    Returns {"text", "translation"}; offered when the user adds a sentence.
    """
    translations = {text.lower() for text in term.native_variants}
    for name in settings.SUGGESTION_PROVIDERS:
        provider = PROVIDERS.get(name)
        if provider is None:
            continue
        result = provider.example(
            term.main_foreign, term.foreign_language.code, term.native_language.code, translations
        )
        if result is not None:
            return result
    return None


def other_meanings(term, include_dictionary=True):
    """Other meanings of the foreign word of a user's word (spec 5.2).

    First the user's own words with the same foreign text (e.g. palm → palma next to
    palm → dlaň), then meanings from the dictionary the user does not have yet.
    Returns a list of dicts: translation ("dárek; dar"), variants (["dárek", "dar"]),
    part_of_speech (short) and own (True for the user's words).
    Nothing is stored: the dictionary part is always read fresh.
    With include_dictionary=False only the user's own words are returned.
    """
    from vocabulary.models import Term

    known = {text.lower() for text in term.native_variants}
    meanings = []
    own = (
        Term.objects.filter(
            owner_id=term.owner_id,
            foreign_language_id=term.foreign_language_id,
            native_language_id=term.native_language_id,
            main_foreign__iexact=term.main_foreign,
        )
        .exclude(pk=term.pk)
        .prefetch_related("variants")
        .order_by("main_native")
    )
    for other in own:
        meanings.append(
            {
                "translation": "; ".join(other.native_variants),
                "variants": other.native_variants,
                "part_of_speech": "",
                "own": True,
            }
        )
        known.update(text.lower() for text in other.native_variants)
    if not include_dictionary:
        return meanings

    result = get_suggestions(
        term.main_foreign, term.foreign_language.code, term.native_language.code
    )
    for suggestion in result.suggestions if result else []:
        variants = parse_variants(suggestion.translation)
        if {text.lower() for text in variants} & known:
            continue
        meanings.append(
            {
                "translation": suggestion.translation,
                "variants": variants,
                "part_of_speech": suggestion.short_pos,
                "own": False,
            }
        )
    return meanings
