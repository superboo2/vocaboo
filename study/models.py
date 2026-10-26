import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


class Direction(models.TextChoices):
    # F = foreign language, N = native language
    F2N = "F2N", _("foreign → native")
    N2F = "N2F", _("native → foreign")


class Result(models.TextChoices):
    """How well the user knew the word; every rating button has one."""

    CORRECT = "correct", _("correct")
    PARTIAL = "partial", _("partial")
    WRONG = "wrong", _("wrong")


class ReviewState(models.Model):
    """When a word should come back in a test, separately for each direction."""

    term = models.ForeignKey(
        "vocabulary.Term",
        verbose_name=_("word"),
        on_delete=models.CASCADE,
        related_name="review_states",
    )
    direction = models.CharField(_("direction"), max_length=3, choices=Direction.choices)
    # Null means the card was never reviewed (new card)
    due_at = models.DateTimeField(_("next review"), null=True, blank=True, db_index=True)
    last_reviewed_at = models.DateTimeField(_("last reviewed"), null=True, blank=True)
    last_rating = models.CharField(_("last rating"), max_length=20, blank=True)
    last_interval = models.DurationField(_("last interval"), null=True, blank=True)
    correct_streak = models.PositiveIntegerField(_("correct in a row"), default=0)
    lapses = models.PositiveIntegerField(_("number of mistakes"), default=0)
    reviews_count = models.PositiveIntegerField(_("number of reviews"), default=0)

    class Meta:
        verbose_name = _("review state")
        verbose_name_plural = _("review states")
        constraints = [
            models.UniqueConstraint(fields=["term", "direction"], name="unique_review_state"),
        ]

    def __str__(self):
        return f"{self.term} ({self.direction})"


class StudyDirection(models.TextChoices):
    """Direction chosen for a test; MIXED means both directions."""

    F2N = "F2N", _("foreign → native")
    N2F = "N2F", _("native → foreign")
    MIXED = "MIXED", _("foreign → native + native → foreign")


class StudyScope(models.TextChoices):
    DUE = "due", _("only due and new")
    ALL = "all", pgettext_lazy("study scope", "all")


def new_shuffle_seed():
    return secrets.randbelow(2**31)


class StudySession(models.Model):
    """One test. It keeps only the settings; the next card is always computed again."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="study_sessions",
    )
    # Child decks are included automatically
    decks = models.ManyToManyField("vocabulary.Deck", verbose_name=_("decks"), blank=True)
    # When set, only these words are tested (e.g. "practise the wrong ones again")
    terms = models.ManyToManyField("vocabulary.Term", verbose_name=_("words"), blank=True)
    direction = models.CharField(
        _("direction"), max_length=5, choices=StudyDirection.choices, default=StudyDirection.MIXED
    )
    scope = models.CharField(
        _("scope"), max_length=3, choices=StudyScope.choices, default=StudyScope.DUE
    )
    max_cards = models.PositiveIntegerField(_("max. number of cards"), null=True, blank=True)
    started_at = models.DateTimeField(_("start"), auto_now_add=True)
    finished_at = models.DateTimeField(_("end"), null=True, blank=True)
    answered = models.PositiveIntegerField(_("answers"), default=0)
    correct = models.PositiveIntegerField(_("correct"), default=0)
    # Random number for the order of the cards: every test has its own order, and it stays
    # the same for the whole test (the next card is computed again for every answer)
    shuffle_seed = models.PositiveIntegerField(_("random order"), default=new_shuffle_seed)

    class Meta:
        verbose_name = _("session")
        verbose_name_plural = _("sessions")

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
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="review_logs",
    )
    term = models.ForeignKey(
        "vocabulary.Term",
        verbose_name=_("word"),
        on_delete=models.CASCADE,
        related_name="review_logs",
    )
    session = models.ForeignKey(
        StudySession,
        verbose_name=_("session"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
    )
    direction = models.CharField(_("direction"), max_length=3, choices=Direction.choices)
    rating = models.CharField(_("rating"), max_length=20)
    rating_label = models.CharField(_("button name"), max_length=100)
    result = models.CharField(_("result"), max_length=10, choices=Result.choices)
    chosen_interval = models.DurationField(_("interval"))
    # Time from showing the card to turning it, and from turning it to rating (ms)
    think_ms = models.PositiveIntegerField(_("thinking (ms)"), null=True, blank=True)
    decide_ms = models.PositiveIntegerField(_("deciding (ms)"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("time"), default=timezone.now)

    class Meta:
        verbose_name = _("answer")
        verbose_name_plural = _("answer history")
        indexes = [
            models.Index(fields=["user", "term", "reviewed_at"], name="reviewlog_user_term_time"),
        ]

    def __str__(self):
        return f"{self.term} {self.direction} {self.rating}"

    @property
    def shown_label(self):
        """The button name in the language of the page; a button that is gone keeps its
        saved name (rating_label is in the language of the moment of the answer)."""
        from .ratings import RATINGS_BY_KEY

        rating = RATINGS_BY_KEY.get(self.rating)
        return rating.label if rating else self.rating_label
