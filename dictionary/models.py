from django.conf import settings
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


class LexiconTag(models.Model):
    """Topic or style of a meaning, e.g. "zvířata" under "příroda" (two levels)."""

    slug = models.SlugField(_("code"), max_length=50, unique=True)
    name = models.CharField(_("name"), max_length=100)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent tag"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    class Meta:
        verbose_name = _("dictionary tag")
        verbose_name_plural = _("dictionary tags")
        ordering = ["slug"]

    def __str__(self):
        return self.name


class PartOfSpeech(models.TextChoices):
    NOUN = "noun", _("noun")
    VERB = "verb", _("verb")
    ADJECTIVE = "adjective", _("adjective")
    ADVERB = "adverb", _("adverb")
    PRONOUN = "pronoun", _("pronoun")
    DETERMINER = "determiner", _("determiner")
    PREPOSITION = "preposition", _("preposition")
    CONJUNCTION = "conjunction", _("conjunction")
    INTERJECTION = "interjection", _("interjection")
    NUMERAL = "numeral", _("numeral")
    PHRASAL_VERB = "phrasal_verb", _("phrasal verb")
    PHRASE = "phrase", _("phrase")


class Concept(models.Model):
    """One meaning, the same in all languages (spec 5.2, docs/slovnik.md).

    The words of every language point to concepts, so two languages meet in a concept, not in
    an English word: "palm" has the concepts palm.noun.1 (dlaň) and palm.noun.2 (palma).
    The key never changes; the English sentence says what the concept means.
    """

    # Stable name used in the files, e.g. "palm.noun.1" (word, part of speech, number)
    key = models.CharField(_("key"), max_length=200, unique=True)
    tags = models.ManyToManyField(LexiconTag, verbose_name=_("tags"), blank=True)
    # Which file it came from: "base", or the package of new words, e.g. "2026-10-19"
    source = models.CharField(_("source"), max_length=20, default="base", db_index=True)

    class Meta:
        verbose_name = _("concept")
        verbose_name_plural = _("concepts")
        ordering = ["key"]

    def __str__(self):
        return self.key


class ConceptText(models.Model):
    """A concept in one language: its words as a translation, the example sentence, a note.

    A language without a text has no translation for the concept yet (they are added bit by
    bit); the suggestions of that pair then leave the concept out.
    """

    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="texts")
    # ISO 639-1 code, e.g. "cs"
    language = models.CharField(_("language"), max_length=2)
    # The words of the concept in this language, variants separated by "; " (the same format
    # as the words of the users): "kočka; kocour"
    words = models.CharField(_("words"), max_length=300)
    # Short hint for readers of this language that tells meanings apart, e.g. "o místě"
    note = models.CharField(_("note"), max_length=200, blank=True)
    # The word is marked with braces, the same format as the sentences of the users
    sentence = models.TextField(_("sentence"), blank=True)

    class Meta:
        verbose_name = _("concept text")
        verbose_name_plural = _("concept texts")
        constraints = [
            models.UniqueConstraint(F("concept"), F("language"), name="unique_concept_text"),
        ]

    def __str__(self):
        return f"{self.language}: {self.words}"


class ConceptTextForm(models.Model):
    """One word of a concept text in lower case ("kočka" and "kocour" of "kočka; kocour"), so a
    typed word is found in the column of its language: CS → EN finds "kočka" in the Czech texts.

    Made by the import from the texts, never written by hand.
    """

    text = models.ForeignKey(ConceptText, on_delete=models.CASCADE, related_name="forms")
    form = models.CharField(_("form"), max_length=300, db_index=True)

    class Meta:
        verbose_name = _("concept text form")
        verbose_name_plural = _("concept text forms")

    def __str__(self):
        return self.form


class LexiconWord(models.Model):
    """A word of one language with one part of speech, with its data (forms, IPA, frequency).

    Its meanings are links to concepts (WordSense). Only languages that are learned as foreign
    languages need words; a language that is only a translation has just concept texts.
    """

    PartOfSpeech = PartOfSpeech

    # ISO 639-1 code, e.g. "en"
    language = models.CharField(_("language"), max_length=2)
    word = models.CharField(pgettext_lazy("dictionary entry", "word"), max_length=200)
    part_of_speech = models.CharField(_("part of speech"), max_length=20, choices=PartOfSpeech)
    # How common the word is in spoken language: 1 = the most common 1000 words, 2 = the next
    # 1000 and so on
    band = models.PositiveSmallIntegerField(_("frequency band"))
    # CEFR level, A1 to C2
    level = models.CharField(_("level"), max_length=2)
    # Pronunciation in IPA without brackets, e.g. "pɑːm"
    ipa = models.CharField(_("pronunciation"), max_length=200, blank=True)
    # Grammatical gender where the language has it, e.g. "f", "m", "n"
    gender = models.CharField(_("gender"), max_length=10, blank=True)
    source = models.CharField(_("source"), max_length=20, default="base", db_index=True)

    class Meta:
        verbose_name = _("dictionary word")
        verbose_name_plural = _("dictionary words")
        constraints = [
            models.UniqueConstraint(
                F("language"), Lower("word"), F("part_of_speech"), name="unique_lexicon_word"
            ),
        ]

    def __str__(self):
        return f"{self.word} ({self.language}, {self.get_part_of_speech_display()})"


class WordForm(models.Model):
    """A text the word is found by: the word itself and its other forms (mum, palms, clung).

    Stored in lower case, so looking up a typed word is one indexed query.
    """

    word = models.ForeignKey(LexiconWord, on_delete=models.CASCADE, related_name="forms")
    text = models.CharField(_("form"), max_length=200, db_index=True)

    class Meta:
        verbose_name = _("word form")
        verbose_name_plural = _("word forms")

    def __str__(self):
        return self.text


class WordSense(models.Model):
    """One meaning of a word: the link of the word to a concept, the most common first."""

    word = models.ForeignKey(LexiconWord, on_delete=models.CASCADE, related_name="senses")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="senses")
    position = models.PositiveSmallIntegerField(_("position"))

    class Meta:
        verbose_name = _("word meaning")
        verbose_name_plural = _("word meanings")
        ordering = ["word", "position"]
        constraints = [
            models.UniqueConstraint(F("word"), F("concept"), name="unique_word_sense"),
        ]

    def __str__(self):
        return f"{self.word.word} → {self.concept.key}"


class LexiconPackage(models.Model):
    """A package of dictionary/data/extensions/ that is in the database already.

    Translations add only texts, which do not remember their package, so this list tells
    extend_lexicon --new which packages are new (deploy/deploy.sh runs it).
    """

    # The folder name, e.g. "2026-11-02"
    name = models.CharField(_("package"), max_length=20, unique=True)
    applied_at = models.DateTimeField(_("added"), auto_now=True)

    class Meta:
        verbose_name = _("dictionary package")
        verbose_name_plural = _("dictionary packages")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ErrorReport(models.Model):
    """A mistake in a suggested translation or sentence that a user reported on the word page
    or in a test.

    Keeps a copy of the word as it was when reported (the word can change or be deleted
    later). The command reported_words lists the open ones for the next fix round of the
    dictionary (docs/slovnik.md); an admin marks them resolved.
    """

    class Kind(models.TextChoices):
        # The hints of the app suggested a wrong translation of the word
        TRANSLATION = "translation", _("Wrong suggested translation")
        # The suggested sentence or its translation does not fit the meaning of the word
        SENTENCE = "sentence", _("Wrong suggested sentence")
        OTHER = "other", _("Something else")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="error_reports",
    )
    term = models.ForeignKey(
        "vocabulary.Term",
        verbose_name=pgettext_lazy("dictionary entry", "word"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="error_reports",
    )
    # The copy of the word: language codes (e.g. "en", "cs") and the variants joined by "; "
    foreign_language = models.CharField(_("language to learn"), max_length=2)
    native_language = models.CharField(_("language I speak"), max_length=2)
    foreign = models.CharField(_("foreign word"), max_length=500)
    native = models.CharField(_("translation"), max_length=500)
    sentence = models.TextField(_("sentence"), blank=True)
    sentence_native = models.TextField(_("sentence translation"), blank=True)
    kind = models.CharField(_("what is wrong"), max_length=20, choices=Kind)
    note = models.TextField(_("note"), blank=True)
    resolved = models.BooleanField(_("resolved"), default=False)
    created_at = models.DateTimeField(_("reported"), auto_now_add=True)
    updated_at = models.DateTimeField(_("changed"), auto_now=True)

    class Meta:
        verbose_name = _("error report")
        verbose_name_plural = _("error reports")
        ordering = ["-created_at"]
        constraints = [
            # One open report of a user for one word: reporting again changes it
            models.UniqueConstraint(
                F("user"),
                F("term"),
                condition=models.Q(resolved=False),
                name="unique_open_error_report",
            ),
        ]

    def __str__(self):
        return f"{self.foreign} → {self.native}"
