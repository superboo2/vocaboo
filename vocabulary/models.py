from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class Language(models.Model):
    # ISO 639-1 code, two lowercase letters, e.g. "cs", "en"
    code = models.CharField(
        _("kód"),
        max_length=2,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z]{2}$",
                _("Zadej dvoupísmenný kód ISO 639-1 malými písmeny, např. cs nebo en."),
            )
        ],
        help_text=_("ISO 639-1, např. cs, en, es. Pozor: čeština je cs, ne cz."),
    )
    name = models.CharField(_("název"), max_length=50)

    class Meta:
        verbose_name = _("jazyk")
        verbose_name_plural = _("jazyky")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Deck(models.Model):
    """A dictionary (folder of words). Decks form a tree, see services.py for the rules."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("vlastník"),
        on_delete=models.CASCADE,
        related_name="decks",
    )
    # Null means a root deck
    parent = models.ForeignKey(
        "self",
        verbose_name=_("nadřazený slovník"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    name = models.CharField(_("název"), max_length=100)
    description = models.TextField(_("popis"), blank=True)
    # Stored on every deck (copied from the parent) to keep queries simple
    foreign_language = models.ForeignKey(
        Language,
        verbose_name=_("chci se naučit"),
        on_delete=models.PROTECT,
        related_name="+",
    )
    native_language = models.ForeignKey(
        Language,
        verbose_name=_("mluvím"),
        on_delete=models.PROTECT,
        related_name="+",
    )
    # Order among siblings, lower number goes first
    position = models.PositiveIntegerField(_("pořadí"), default=0)
    created_at = models.DateTimeField(_("vytvořeno"), auto_now_add=True)

    class Meta:
        verbose_name = _("slovník")
        verbose_name_plural = _("slovníky")
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
                violation_error_message=_("Slovník s tímto názvem už tu existuje."),
            ),
            models.CheckConstraint(
                condition=~Q(foreign_language=F("native_language")),
                name="deck_languages_differ",
                violation_error_message=_(
                    "Jazyk, který se chceš naučit, a jazyk, kterým mluvíš, musí být různé."
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
        MANUAL = "manual", _("ručně")
        TRANSLATED = "translated", _("překladač")
        VOICE = "voice", _("hlas")
        IMPORT = "import", _("import")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("vlastník"),
        on_delete=models.CASCADE,
        related_name="terms",
    )
    foreign_language = models.ForeignKey(
        Language, verbose_name=_("chci se naučit"), on_delete=models.PROTECT, related_name="+"
    )
    native_language = models.ForeignKey(
        Language, verbose_name=_("mluvím"), on_delete=models.PROTECT, related_name="+"
    )
    # Copies of the main variants, for the unique constraint and quick lookups.
    # Words with the same spelling and another translation are other meanings:
    # palm → dlaň and palm → palma are two words.
    main_foreign = models.CharField(_("hlavní cizí varianta"), max_length=200)
    main_native = models.CharField(_("hlavní překlad"), max_length=200)
    note = models.TextField(_("poznámka"), blank=True)
    origin = models.CharField(
        _("původ"), max_length=20, choices=Origin.choices, default=Origin.MANUAL
    )
    created_at = models.DateTimeField(_("vytvořeno"), auto_now_add=True)

    class Meta:
        verbose_name = _("slovíčko")
        verbose_name_plural = _("slovíčka")
        constraints = [
            models.UniqueConstraint(
                F("owner"),
                F("foreign_language"),
                F("native_language"),
                Lower("main_foreign"),
                Lower("main_native"),
                name="unique_term",
                violation_error_message=_("Toto slovíčko už máš."),
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
        FOREIGN = "F", _("cizí")
        NATIVE = "N", _("rodná")

    term = models.ForeignKey(
        Term, verbose_name=_("slovíčko"), on_delete=models.CASCADE, related_name="variants"
    )
    side = models.CharField(_("strana"), max_length=1, choices=Side.choices)
    text = models.CharField(_("text"), max_length=200)
    position = models.PositiveSmallIntegerField(_("pořadí"), default=0)

    class Meta:
        verbose_name = _("varianta")
        verbose_name_plural = _("varianty")
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
        Deck, verbose_name=_("slovník"), on_delete=models.CASCADE, related_name="deck_terms"
    )
    term = models.ForeignKey(
        Term, verbose_name=_("slovíčko"), on_delete=models.CASCADE, related_name="deck_terms"
    )
    # Sentence where the word was seen, e.g. "Hello, Penny."
    context_sentence = models.TextField(_("věta"), blank=True)
    # Its translation, e.g. "Ahoj, Penny." (only to understand it; on the card in both directions)
    context_sentence_native = models.TextField(_("překlad věty"), blank=True)
    added_at = models.DateTimeField(_("přidáno"), auto_now_add=True)

    class Meta:
        verbose_name = _("slovíčko ve slovníku")
        verbose_name_plural = _("slovíčka ve slovnících")
        constraints = [
            models.UniqueConstraint(fields=["deck", "term"], name="unique_deck_term"),
        ]

    def __str__(self):
        return f"{self.term} @ {self.deck}"
