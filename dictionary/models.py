from django.db import models
from django.db.models import F
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class LexiconTag(models.Model):
    """Topic or style of a meaning, e.g. "zvířata" under "příroda" (two levels)."""

    slug = models.SlugField(_("kód"), max_length=50, unique=True)
    name = models.CharField(_("název"), max_length=100)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("nadřazený tag"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    class Meta:
        verbose_name = _("tag slovníku")
        verbose_name_plural = _("tagy slovníku")
        ordering = ["slug"]

    def __str__(self):
        return self.name


class LexiconEntry(models.Model):
    """One headword of the dictionary of the app: a word with one part of speech.

    It is reference data, separate from the words of the users. Filled by the command
    import_lexicon; importing again replaces all entries of the same language pair.
    """

    class PartOfSpeech(models.TextChoices):
        NOUN = "noun", _("podstatné jméno")
        VERB = "verb", _("sloveso")
        ADJECTIVE = "adjective", _("přídavné jméno")
        ADVERB = "adverb", _("příslovce")
        PRONOUN = "pronoun", _("zájmeno")
        DETERMINER = "determiner", _("determinátor")
        PREPOSITION = "preposition", _("předložka")
        CONJUNCTION = "conjunction", _("spojka")
        INTERJECTION = "interjection", _("citoslovce")
        NUMERAL = "numeral", _("číslovka")
        PHRASAL_VERB = "phrasal_verb", _("frázové sloveso")
        PHRASE = "phrase", _("fráze")

    # ISO 639-1 codes: the word is in foreign_code, its meanings are in native_code
    foreign_code = models.CharField(_("jazyk slova"), max_length=2)
    native_code = models.CharField(_("jazyk významů"), max_length=2)
    word = models.CharField(_("slovo"), max_length=200)
    part_of_speech = models.CharField(_("slovní druh"), max_length=20, choices=PartOfSpeech)
    # How common the word is in spoken language: 1 = the most common 1000 words, 2 = the next
    # 1000 and so on
    band = models.PositiveSmallIntegerField(_("pásmo častosti"))
    # CEFR level, A1 to C2
    level = models.CharField(_("úroveň"), max_length=2)
    # Pronunciation in IPA without brackets, e.g. "pɑːm"
    ipa = models.CharField(_("výslovnost"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("heslo slovníku")
        verbose_name_plural = _("hesla slovníku")
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
    text = models.CharField(_("tvar"), max_length=200, db_index=True)

    class Meta:
        verbose_name = _("tvar hesla")
        verbose_name_plural = _("tvary hesla")

    def __str__(self):
        return self.text


class LexiconSense(models.Model):
    """One meaning of an entry, with its translation and an example sentence."""

    entry = models.ForeignKey(LexiconEntry, on_delete=models.CASCADE, related_name="senses")
    # The most common meaning first
    position = models.PositiveSmallIntegerField(_("pořadí"))
    # Variants separated by "; ", the same format as the words of the users
    translation = models.CharField(_("překlad"), max_length=300)
    # Short hint that tells the meanings apart, e.g. "váha", "hovorově"
    note = models.CharField(_("poznámka"), max_length=200, blank=True)
    # The word is marked with braces, the same format as the sentences of the users
    sentence = models.TextField(_("věta"))
    sentence_native = models.TextField(_("překlad věty"), blank=True)
    tags = models.ManyToManyField(LexiconTag, verbose_name=_("tagy"), blank=True)

    class Meta:
        verbose_name = _("význam hesla")
        verbose_name_plural = _("významy hesla")
        ordering = ["entry", "position"]

    def __str__(self):
        return self.translation
