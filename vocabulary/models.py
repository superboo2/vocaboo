from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

# Names of languages in the language of the page, by ISO 639-1 code; a language that is not
# here shows the name saved in the database
LANGUAGE_NAMES = {
    "cs": _("Czech"),
    "de": _("German"),
    "en": _("English"),
    "es": _("Spanish"),
    "fr": _("French"),
    "it": _("Italian"),
    "ja": _("Japanese"),
    "nl": _("Dutch"),
    "pl": _("Polish"),
    "pt": _("Portuguese"),
    "ru": _("Russian"),
    "sk": _("Slovak"),
    "uk": _("Ukrainian"),
    "zh": _("Chinese"),
}


class Language(models.Model):
    # ISO 639-1 code, two lowercase letters, e.g. "cs", "en"
    code = models.CharField(
        _("code"),
        max_length=2,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z]{2}$",
                _("Enter a two-letter ISO 639-1 code in lowercase, for example, cs or en."),
            )
        ],
        help_text=_("ISO 639-1, for example, cs, en, es. Note: Czech is cs, not cz."),
    )
    name = models.CharField(_("name"), max_length=50)

    class Meta:
        verbose_name = _("language")
        verbose_name_plural = _("languages")
        ordering = ["name"]

    def __str__(self):
        return str(self.label)

    @property
    def label(self):
        """The name in the language of the page, e.g. "English" or "Angličtina"."""
        return LANGUAGE_NAMES.get(self.code, self.name)


class Deck(models.Model):
    """A dictionary (folder of words). Decks form a tree, see services.py for the rules."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("owner"),
        on_delete=models.CASCADE,
        related_name="decks",
    )
    # Null means a root deck
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent deck"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    # Stored on every deck (copied from the parent) to keep queries simple
    foreign_language = models.ForeignKey(
        Language,
        verbose_name=_("language to learn"),
        on_delete=models.PROTECT,
        related_name="+",
    )
    native_language = models.ForeignKey(
        Language,
        verbose_name=_("language I speak"),
        on_delete=models.PROTECT,
        related_name="+",
    )
    # Order among siblings, lower number goes first
    position = models.PositiveIntegerField(_("position"), default=0)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        verbose_name = _("deck")
        verbose_name_plural = _("decks")
        ordering = ["position", "name", "pk"]
        constraints = [
            # Same name only once under one parent, ignoring letter case.
            # nulls_distinct=False makes it work for root decks (parent is NULL) too.
            models.UniqueConstraint(
                Lower("name"),
                F("owner"),
                F("parent"),
                nulls_distinct=False,
                name="unique_deck_name_per_parent",
                violation_error_message=_("A deck with this name already exists here."),
            ),
            models.CheckConstraint(
                condition=~Q(foreign_language=F("native_language")),
                name="deck_languages_differ",
                violation_error_message=_(
                    "The language you want to learn and the language you speak must be different."
                ),
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def language_pair(self):
        # For example "EN → CS"
        return f"{self.foreign_language.code.upper()} → {self.native_language.code.upper()}"


class Term(models.Model):
    """One word: "cizí výraz ↔ překlad". It belongs to the user, decks only point to it.

    The texts are in TermVariant, both sides can have more variants (synonyms).
    """

    class Origin(models.TextChoices):
        MANUAL = "manual", _("manual")
        TRANSLATED = "translated", _("translator")
        VOICE = "voice", _("voice")
        IMPORT = "import", _("import")
        # Ticked on the page "Words from a topic" (dictionary of the app)
        DICTIONARY = "dictionary", _("dictionary")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("owner"),
        on_delete=models.CASCADE,
        related_name="terms",
    )
    foreign_language = models.ForeignKey(
        Language, verbose_name=_("language to learn"), on_delete=models.PROTECT, related_name="+"
    )
    native_language = models.ForeignKey(
        Language, verbose_name=_("language I speak"), on_delete=models.PROTECT, related_name="+"
    )
    # Copies of the main variants, for the unique constraint and quick lookups.
    # Words with the same spelling and another translation are other meanings:
    # palm → dlaň and palm → palma are two words.
    main_foreign = models.CharField(_("main foreign variant"), max_length=200)
    main_native = models.CharField(_("main translation"), max_length=200)
    note = models.TextField(_("note"), blank=True)
    origin = models.CharField(
        _("origin"), max_length=20, choices=Origin.choices, default=Origin.MANUAL
    )
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        verbose_name = _("word")
        verbose_name_plural = _("words")
        constraints = [
            models.UniqueConstraint(
                F("owner"),
                F("foreign_language"),
                F("native_language"),
                Lower("main_foreign"),
                Lower("main_native"),
                name="unique_term",
                violation_error_message=_("You already have this word."),
            ),
        ]

    def __str__(self):
        return f"{self.main_foreign} → {self.main_native}"

    def _variants(self, side):
        # Uses prefetched variants when they are there (prefetch_related("variants"))
        return [v.text for v in self.variants.all() if v.side == side]

    @property
    def foreign_variants(self):
        return self._variants(TermVariant.Side.FOREIGN)

    @property
    def native_variants(self):
        return self._variants(TermVariant.Side.NATIVE)


class TermVariant(models.Model):
    """One text of a word. Position 0 is the main variant of its side."""

    class Side(models.TextChoices):
        FOREIGN = "F", _("foreign")
        NATIVE = "N", _("native")

    term = models.ForeignKey(
        Term, verbose_name=_("word"), on_delete=models.CASCADE, related_name="variants"
    )
    side = models.CharField(_("side"), max_length=1, choices=Side.choices)
    text = models.CharField(_("text"), max_length=200)
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("variant")
        verbose_name_plural = _("variants")
        ordering = ["side", "position"]
        constraints = [
            models.UniqueConstraint(
                F("term"), F("side"), Lower("text"), name="unique_term_variant"
            ),
        ]

    def __str__(self):
        return self.text


class DeckTerm(models.Model):
    """A word placed in a deck, with the sentence where it was seen."""

    deck = models.ForeignKey(
        Deck, verbose_name=_("deck"), on_delete=models.CASCADE, related_name="deck_terms"
    )
    term = models.ForeignKey(
        Term, verbose_name=_("word"), on_delete=models.CASCADE, related_name="deck_terms"
    )
    # Sentence where the word was seen, e.g. "Hello, Penny."
    context_sentence = models.TextField(_("sentence"), blank=True)
    # Its translation, e.g. "Ahoj, Penny." (only to understand it; on the card in both directions)
    context_sentence_native = models.TextField(_("sentence translation"), blank=True)
    added_at = models.DateTimeField(_("added"), auto_now_add=True)

    class Meta:
        verbose_name = _("word in deck")
        verbose_name_plural = _("words in decks")
        constraints = [
            models.UniqueConstraint(fields=["deck", "term"], name="unique_deck_term"),
        ]

    def __str__(self):
        return f"{self.term} @ {self.deck}"
