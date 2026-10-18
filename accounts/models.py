from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from study.models import StudyDirection


class UserManager(DjangoUserManager):
    """Manager for a user that logs in with email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        # Login with any letter case: "Martin@x.cz" finds "martin@x.cz"
        return self.get(email__iexact=username)


class User(AbstractUser):
    username = None
    email = models.EmailField(_("email"), unique=True)
    # Used as default native language for new decks
    native_language = models.ForeignKey(
        "vocabulary.Language",
        verbose_name=_("native language"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Direction chosen in a new test unless the user picks another one
    default_direction = models.CharField(
        _("default test direction"),
        max_length=5,
        choices=StudyDirection.choices,
        default=StudyDirection.MIXED,
    )
    # Translation suggestions from the dictionary while a new word is typed
    show_suggestions = models.BooleanField(_("suggest translations"), default=True)
    # Meanings from the dictionary on the back of a test card (the user's own are always shown)
    show_other_meanings = models.BooleanField(_("other meanings on the card"), default=True)

    class AutoplayContent(models.TextChoices):
        WORD = "word", pgettext_lazy("autoplay", "word")
        SENTENCE = "sentence", _("the whole sentence")

    # Read the foreign word aloud by itself: foreign → native when the card comes,
    # native → foreign after it is turned
    autoplay_pronunciation = models.BooleanField(_("play automatically"), default=True)
    # What is read: the word, or the sentence of the card (the word when there is none)
    autoplay_content = models.CharField(
        _("what to play"), max_length=10, choices=AutoplayContent, default=AutoplayContent.WORD
    )
    # Written pronunciation in IPA, e.g. [pɑːm], on the card and on the word page
    show_ipa = models.BooleanField(_("written pronunciation (IPA)"), default=False)

    # Language of the app (menus, buttons, help); empty = as the browser asks
    ui_language = models.CharField(
        _("app language"), max_length=10, choices=settings.LANGUAGES, blank=True
    )

    USERNAME_FIELD = "email"
    # Fields asked by createsuperuser besides email and password
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"),
        ]

    def __str__(self):
        return self.email
