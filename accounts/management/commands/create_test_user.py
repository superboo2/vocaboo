"""Create an account for trying the app, without the registration form and the email code.
The password is the same as the email. Only with DEBUG (never on the server).

    uv run python manage.py create_test_user                  # test1@example.cz (the first free)
    uv run python manage.py create_test_user --language it    # native Italian, Italian first deck
    uv run python manage.py create_test_user --email me@example.cz --language uk --ui uk

The account is turned on at once and gets the first deck, as after a confirmed email.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from dictionary import starter
from vocabulary.models import Language

EMAIL = "test{number}@example.cz"


def free_email():
    """The test email with the lowest free number: test1, test2 …"""
    number = 1
    while User.objects.filter(email__iexact=EMAIL.format(number=number)).exists():
        number += 1
    return EMAIL.format(number=number)


class Command(BaseCommand):
    help = "Create a turned-on account for tests (password = email). Only with DEBUG."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Default: the first free testN@example.cz")
        parser.add_argument(
            "--language", default="cs", help="Native language, e.g. cs, it, uk (default cs)"
        )
        parser.add_argument(
            "--ui", default="", help="Language of the app, e.g. cs, de, uk; default: the browser"
        )

    def handle(self, *args, email=None, language="cs", ui="", **options):
        if not settings.DEBUG:
            raise CommandError("Only for development: DJANGO_DEBUG is off.")
        native = Language.objects.filter(code=language).first()
        if native is None:
            raise CommandError(f"Unknown language {language!r}.")
        if ui and ui not in dict(settings.LANGUAGES):
            codes = ", ".join(code for code, _name in settings.LANGUAGES)
            raise CommandError(f"The app is not translated into {ui!r} (only {codes}).")
        email = User.objects.normalize_email(email).lower() if email else free_email()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"{email} already exists.")

        # No password rules: the password is the email, only for trying
        user = User.objects.create_user(
            email=email, password=email, native_language=native, ui_language=ui, is_active=True
        )
        root = starter.create_first_deck(user)
        if root:
            self.stdout.write(f"First deck: {root.name}")
        self.stdout.write(self.style.SUCCESS(f"{email}  (password: {email})"))
