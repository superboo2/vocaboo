from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Direction(models.TextChoices):
    # F = foreign language, N = native language
    F2N = "F2N", _("cizí → rodný")
    N2F = "N2F", _("rodný → cizí")


class Result(models.TextChoices):
    """How well the user knew the word; every rating button has one."""

    CORRECT = "correct", _("správně")
    PARTIAL = "partial", _("napůl")
    WRONG = "wrong", _("chyba")


class ReviewState(models.Model):
    """When a word should come back in a test, separately for each direction."""

    term = models.ForeignKey(
        "vocabulary.Term",
        verbose_name=_("slovíčko"),
        on_delete=models.CASCADE,
        related_name="review_states",
    )
    direction = models.CharField(_("směr"), max_length=3, choices=Direction.choices)
    # Null means the card was never reviewed (new card)
    due_at = models.DateTimeField(_("další opakování"), null=True, blank=True, db_index=True)
    last_reviewed_at = models.DateTimeField(_("naposledy opakováno"), null=True, blank=True)
    last_rating = models.CharField(_("poslední hodnocení"), max_length=20, blank=True)
    last_interval = models.DurationField(_("poslední interval"), null=True, blank=True)
    correct_streak = models.PositiveIntegerField(_("správně za sebou"), default=0)
    lapses = models.PositiveIntegerField(_("počet chyb"), default=0)
    reviews_count = models.PositiveIntegerField(_("počet opakování"), default=0)

    class Meta:
        verbose_name = _("stav opakování")
        verbose_name_plural = _("stavy opakování")
        constraints = [
            models.UniqueConstraint(fields=["term", "direction"], name="unique_review_state"),
        ]

    def __str__(self):
        return f"{self.term} ({self.direction})"


class StudyDirection(models.TextChoices):
    """Direction chosen for a test; MIXED means both directions."""

    F2N = "F2N", _("cizí → rodný")
    N2F = "N2F", _("rodný → cizí")
    MIXED = "MIXED", _("zamíchat")


class StudyScope(models.TextChoices):
    DUE = "due", _("jen k opakování a nová")
    ALL = "all", _("všechna")


class StudySession(models.Model):
    """One test. It keeps only the settings; the next card is always computed again."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("uživatel"),
        on_delete=models.CASCADE,
        related_name="study_sessions",
    )
    # Child decks are included automatically
    decks = models.ManyToManyField("vocabulary.Deck", verbose_name=_("slovníky"), blank=True)
    # When set, only these words are tested (e.g. "practise the wrong ones again")
    terms = models.ManyToManyField("vocabulary.Term", verbose_name=_("slovíčka"), blank=True)
    direction = models.CharField(
        _("směr"), max_length=5, choices=StudyDirection.choices, default=StudyDirection.MIXED
    )
    scope = models.CharField(
        _("rozsah"), max_length=3, choices=StudyScope.choices, default=StudyScope.DUE
    )
    max_cards = models.PositiveIntegerField(_("max. počet karet"), null=True, blank=True)
    started_at = models.DateTimeField(_("začátek"), auto_now_add=True)
    finished_at = models.DateTimeField(_("konec"), null=True, blank=True)
    answered = models.PositiveIntegerField(_("odpovědí"), default=0)
    correct = models.PositiveIntegerField(_("správně"), default=0)

    class Meta:
        verbose_name = _("sezení")
        verbose_name_plural = _("sezení")

    def __str__(self):
        return f"{self.user} {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def directions(self):
        if self.direction == StudyDirection.MIXED:
            return [Direction.F2N, Direction.N2F]
        return [self.direction]


class ReviewLog(models.Model):
    """Every answer, for statistics. Rating, result and interval are copies, so changing
    the buttons later does not change the history."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("uživatel"),
        on_delete=models.CASCADE,
        related_name="review_logs",
    )
    term = models.ForeignKey(
        "vocabulary.Term",
        verbose_name=_("slovíčko"),
        on_delete=models.CASCADE,
        related_name="review_logs",
    )
    session = models.ForeignKey(
        StudySession,
        verbose_name=_("sezení"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
    )
    direction = models.CharField(_("směr"), max_length=3, choices=Direction.choices)
    rating = models.CharField(_("hodnocení"), max_length=20)
    rating_label = models.CharField(_("název tlačítka"), max_length=100)
    result = models.CharField(_("výsledek"), max_length=10, choices=Result.choices)
    chosen_interval = models.DurationField(_("interval"))
    # Time from showing the card to turning it, and from turning it to rating (ms)
    think_ms = models.PositiveIntegerField(_("přemýšlení (ms)"), null=True, blank=True)
    decide_ms = models.PositiveIntegerField(_("rozhodnutí (ms)"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("čas"), default=timezone.now)

    class Meta:
        verbose_name = _("odpověď")
        verbose_name_plural = _("historie odpovědí")
        indexes = [
            models.Index(fields=["user", "term", "reviewed_at"], name="reviewlog_user_term_time"),
        ]

    def __str__(self):
        return f"{self.term} {self.direction} {self.rating}"
