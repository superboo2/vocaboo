"""Translation suggestions shown while a word is typed, other meanings and pronunciation.

Every source is a provider with the same small interface, so sources can be added or
changed later without touching the rest of the app. The order of the sources is the
setting SUGGESTION_PROVIDERS (and PRONUNCIATION_PROVIDERS); the first source that knows the
word wins. Today there is one source: the dictionary of the app (dictionary.models).
"""

from dataclasses import dataclass, field

from django.conf import settings

from vocabulary.services import parse_variants

from .models import LexiconEntry, LexiconSense

# Most suggestions shown for one word
LIMIT = 12

# Short names of parts of speech for the small suggestion buttons
SHORT_POS = {
    "noun": "podst. jm.",
    "verb": "slov.",
    "adjective": "příd. jm.",
    "adverb": "přísl.",
    "pronoun": "zájm.",
    "determiner": "determ.",
    "preposition": "předl.",
    "conjunction": "spoj.",
    "interjection": "cit.",
    "numeral": "čísl.",
    "phrasal_verb": "fráz. slov.",
    "phrase": "fráze",
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
        return SHORT_POS.get(self.part_of_speech, self.part_of_speech)

    @property
    def pos_label(self):
        return LexiconEntry.PartOfSpeech(self.part_of_speech).label if self.part_of_speech else ""


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


def _senses(word, foreign_code, native_code):
    """Meanings of the word (headword or another spelling), the most common first."""
    return (
        LexiconSense.objects.filter(
            entry__forms__text=word.lower(),
            entry__foreign_code=foreign_code,
            entry__native_code=native_code,
        )
        .select_related("entry")
        .order_by("entry__band", "entry_id", "position")
    )


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
                    part_of_speech=sense.entry.part_of_speech,
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
            LexiconEntry.objects.filter(forms__text=word.lower(), foreign_code=foreign_code)
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
