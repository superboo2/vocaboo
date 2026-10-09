"""Translation suggestions shown while a word is typed, and pronunciation of words.

Every source is a provider with the same small interface, so sources can be added or
changed (e.g. a paid service or text to speech later) without touching the rest of the app.
The order of the sources is the setting SUGGESTION_PROVIDERS (and PRONUNCIATION_PROVIDERS);
the first source that knows the word wins.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import quote

from django.conf import settings
from django.db.models.functions import Lower

from vocabulary.services import parse_variants

from .models import DictionaryEntry

# Most suggestions shown for one word
LIMIT = 12

# Short names of parts of speech for the small suggestion buttons
SHORT_POS = {
    "podstatné jméno": "podst. jm.",
    "přídavné jméno": "příd. jm.",
    "zájmeno": "zájm.",
    "číslovka": "čísl.",
    "sloveso": "slov.",
    "příslovce": "přísl.",
    "předložka": "předl.",
    "spojka": "spoj.",
    "částice": "část.",
    "citoslovce": "cit.",
}


@dataclass
class Suggestion:
    # Text for the translation field, variants separated by "; " (e.g. "dárek; dar")
    translation: str
    # Part of speech or another short note, shown next to the suggestion
    part_of_speech: str = ""
    # Note from the source, e.g. "(o dopravě)", shown in small letters
    note: str = ""
    examples: list = field(default_factory=list)

    @property
    def short_pos(self):
        return SHORT_POS.get(self.part_of_speech, self.part_of_speech)


@dataclass
class SuggestionResult:
    suggestions: list
    # Name of the source and a link to it; the licence of Wiktionary needs this
    source_name: str = ""
    source_url: str = ""
    # Short name for texts like "(další významy z Wiktionary)"
    source_label: str = ""


@dataclass
class Pronunciation:
    # Pronunciation in IPA, e.g. "[pɑːm]"
    ipa: str = ""
    # Recording of a real speaker (mp3), played in the browser only after a click
    audio_url: str = ""
    # Short name of the source, e.g. "Wiktionary"
    source_label: str = ""


class Provider:
    name = ""

    def suggest(self, word, foreign_code, native_code):
        """Return a SuggestionResult, or None when the source does not know the word."""
        return None

    def pronounce(self, word, foreign_code):
        """Return a Pronunciation, or None when the source does not know the word."""
        return None


class WiktionaryProvider(Provider):
    """Czech Wiktionary imported by the command import_wiktionary (only meanings in Czech)."""

    name = "wiktionary"

    def suggest(self, word, foreign_code, native_code):
        entries = (
            DictionaryEntry.objects.annotate(word_lower=Lower("word"))
            .filter(
                word_lower=word.lower(),
                foreign_code=foreign_code,
                native_code=native_code,
            )
            .order_by("pk")
        )
        suggestions = []
        seen = set()
        for entry in entries:
            for sense in entry.senses:
                translation, note = split_gloss(sense["text"])
                if not translation or translation.lower() in seen:
                    continue
                seen.add(translation.lower())
                suggestions.append(
                    Suggestion(
                        translation=translation,
                        part_of_speech=entry.part_of_speech,
                        note=note,
                        examples=sense.get("examples", []),
                    )
                )
        if not suggestions:
            return None
        return SuggestionResult(
            suggestions=suggestions[:LIMIT],
            source_name="Wiktionary (CC BY-SA)",
            source_label="Wiktionary",
            source_url=f"https://cs.wiktionary.org/wiki/{quote(entries[0].word)}",
        )

    def pronounce(self, word, foreign_code):
        entries = DictionaryEntry.objects.annotate(word_lower=Lower("word")).filter(
            word_lower=word.lower(), foreign_code=foreign_code
        )
        # IPA and the recording can be in different entries (e.g. noun and verb)
        ipa = entries.exclude(ipa="").order_by("pk").values_list("ipa", flat=True).first()
        audio = (
            entries.exclude(audio_url="").order_by("pk").values_list("audio_url", flat=True).first()
        )
        if not ipa and not audio:
            return None
        # Without the brackets of the source ([pɑːm] or /pɑːm/); the page adds its own
        ipa = (ipa or "").strip().strip("[]/").strip()
        return Pronunciation(ipa=ipa, audio_url=audio or "", source_label="Wiktionary")


PROVIDERS = {provider.name: provider for provider in [WiktionaryProvider()]}

# Text in parentheses, e.g. "(o prostředku dopravy) jezdit"
PARENTHESES = re.compile(r"\(([^()]*)\)")


def split_gloss(gloss):
    """Turn a gloss of Wiktionary into (translation, note).

    "dosavadní, současný, nynější"  -> ("dosavadní; současný; nynější", "")
    "(o dopravě) jezdit, obsluhovat" -> ("jezdit; obsluhovat", "o dopravě")
    Long explanations without a short translation give ("", "") and are not offered.
    """
    notes = [note.strip() for note in PARENTHESES.findall(gloss) if note.strip()]
    text = PARENTHESES.sub(" ", gloss)
    variants = parse_variants(text.replace(",", ";"))
    # A sentence-like explanation is not a translation to learn
    if not variants or any(len(variant.split()) > 4 for variant in variants):
        return "", ""
    return "; ".join(variants), ", ".join(notes)


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
    """Pronunciation of the first variant of the word, from the first source that knows it.

    With with_ipa=False the IPA is left out (the user does not want to see it); then only
    a recording counts and a word without one has no pronunciation.
    """
    variants = parse_variants(word)
    if not variants:
        return None
    for name in settings.PRONUNCIATION_PROVIDERS:
        provider = PROVIDERS.get(name)
        if provider is None:
            continue
        result = provider.pronounce(variants[0], foreign_code)
        if result is not None and not with_ipa:
            result.ipa = ""
        if result is not None and (result.ipa or result.audio_url):
            return result
    return None


def other_meanings(term, include_dictionary=True):
    """Other meanings of the foreign word of a user's word (spec 5.2).

    First the user's own words with the same foreign text (e.g. palm → palma next to
    palm → dlaň), then meanings from the dictionary the user does not have yet.
    Returns a list of dicts: translation ("dárek; dar"), variants (["dárek", "dar"]),
    part_of_speech, own (True for the user's words) and source (short name of the
    dictionary, empty for the user's words).
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
                "source": "",
            }
        )
        known.update(text.lower() for text in other.native_variants)
    if not include_dictionary:
        return meanings

    result = get_suggestions(
        term.main_foreign, term.foreign_language.code, term.native_language.code
    )
    for suggestion in result.suggestions if result else []:
        variants = suggestion.translation.split("; ")
        if {text.lower() for text in variants} & known:
            continue
        meanings.append(
            {
                "translation": suggestion.translation,
                "variants": variants,
                "part_of_speech": suggestion.short_pos,
                "own": False,
                "source": result.source_label,
            }
        )
    return meanings
