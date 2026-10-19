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


class LexiconEntry(models.Model):
    """One headword of the dictionary of the app: a word with one part of speech.

    It is reference data, separate from the words of the users. Filled by the command
    import_lexicon; importing again replaces all entries of the same language pair.
    """

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

    # ISO 639-1 codes: the word is in foreign_code, its meanings are in native_code
    foreign_code = models.CharField(_("word language"), max_length=2)
    native_code = models.CharField(_("meanings language"), max_length=2)
    word = models.CharField(pgettext_lazy("dictionary entry", "word"), max_length=200)
    part_of_speech = models.CharField(_("part of speech"), max_length=20, choices=PartOfSpeech)
    # How common the word is in spoken language: 1 = the most common 1000 words, 2 = the next
    # 1000 and so on
    band = models.PositiveSmallIntegerField(_("frequency band"))
    # CEFR level, A1 to C2
    level = models.CharField(_("level"), max_length=2)
    # Pronunciation in IPA without brackets, e.g. "pɑːm"
    ipa = models.CharField(_("pronunciation"), max_length=200, blank=True)
    # Which file it came from: "base", or the package of new words, e.g. "2026-10-19"
    source = models.CharField(_("source"), max_length=20, default="base", db_index=True)

    class Meta:
        verbose_name = _("dictionary entry")
        verbose_name_plural = _("dictionary entries")
        constraints = [
            models.UniqueConstraint(
                F("foreign_code"),
                F("native_code"),
                Lower("word"),
                F("part_of_speech"),
                name="unique_lexicon_entry",
            ),
        ]

    def __str__(self):
        return f"{self.word} ({self.get_part_of_speech_display()})"


class LexiconForm(models.Model):
    """A text the entry is found by: the headword and its other spellings (mum for mom).

    Stored in lower case, so looking up a typed word is one indexed query.
    """

    entry = models.ForeignKey(LexiconEntry, on_delete=models.CASCADE, related_name="forms")
    text = models.CharField(_("form"), max_length=200, db_index=True)

    class Meta:
        verbose_name = _("entry form")
        verbose_name_plural = _("entry forms")

    def __str__(self):
        return self.text


class LexiconSense(models.Model):
    """One meaning of an entry, with its translation and an example sentence."""

    entry = models.ForeignKey(LexiconEntry, on_delete=models.CASCADE, related_name="senses")
    # The most common meaning first
    position = models.PositiveSmallIntegerField(_("position"))
    # Variants separated by "; ", the same format as the words of the users
    translation = models.CharField(_("translation"), max_length=300)
    # Short hint that tells the meanings apart, e.g. "váha", "hovorově"
    note = models.CharField(_("note"), max_length=200, blank=True)
    # The word is marked with braces, the same format as the sentences of the users
    sentence = models.TextField(_("sentence"))
    sentence_native = models.TextField(_("sentence translation"), blank=True)
    tags = models.ManyToManyField(LexiconTag, verbose_name=_("tags"), blank=True)

    class Meta:
        verbose_name = _("entry meaning")
        verbose_name_plural = _("entry meanings")
        ordering = ["entry", "position"]

    def __str__(self):
        return self.translation
