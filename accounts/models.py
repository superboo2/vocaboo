from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

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
    email = models.EmailField(_("e-mail"), unique=True)
    # Used as default native language for new decks
    native_language = models.ForeignKey(
        "vocabulary.Language",
        verbose_name=_("mluvím"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Direction chosen in a new test unless the user picks another one
    default_direction = models.CharField(
        _("výchozí směr testu"),
        max_length=5,
        choices=StudyDirection.choices,
        default=StudyDirection.MIXED,
    )
    # Translation suggestions from the dictionary while a new word is typed
    show_suggestions = models.BooleanField(_("navrhovat překlad"), default=True)
    # Meanings from the dictionary on the back of a test card (the user's own are always shown)
    show_other_meanings = models.BooleanField(_("další významy na kartě"), default=True)

    USERNAME_FIELD = "email"
    # Fields asked by createsuperuser besides email and password
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("uživatel")
        verbose_name_plural = _("uživatelé")
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"),
        ]

    def __str__(self):
        return self.email
