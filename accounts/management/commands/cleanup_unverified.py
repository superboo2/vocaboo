"""Delete new accounts that never confirmed their email (older than UNVERIFIED_ACCOUNT_DAYS).
Accounts turned off in the admin stay. Run it once a day, e.g. from cron.

    uv run python manage.py cleanup_unverified
    uv run python manage.py cleanup_unverified --dry-run
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User


def unverified_accounts():
    old = timezone.now() - timedelta(days=settings.UNVERIFIED_ACCOUNT_DAYS)
    return User.objects.filter(
        is_active=False, email_verification__isnull=False, date_joined__lt=old
    )


class Command(BaseCommand):
    help = "Delete new accounts that did not confirm their email in time."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only list them.")

    def handle(self, *args, **options):
        accounts = unverified_accounts()
        for user in accounts:
            self.stdout.write(
                f"{'would delete' if options['dry_run'] else 'deleted'}  {user.email}"
            )
        count = accounts.count()
        if not options["dry_run"]:
            accounts.delete()
        self.stdout.write(f"Unverified accounts: {count}.")
