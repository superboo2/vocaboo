"""Texts for the test screen: intervals."""

from datetime import timedelta

from django.utils.translation import gettext as _
from django.utils.translation import ngettext


def format_interval(interval):
    """Short text for an interval, e.g. "10 min", "5 h", "1 day", "8 days", "1 year"."""
    if interval < timedelta(hours=1):
        minutes = max(1, round(interval / timedelta(minutes=1)))
        return _("%(count)s min") % {"count": minutes}
    if interval < timedelta(days=1):
        hours = round(interval / timedelta(hours=1))
        return _("%(count)s h") % {"count": hours}
    days = round(interval / timedelta(days=1))
    if days % 365 == 0:
        years = days // 365
        return ngettext("%(count)s year", "%(count)s years", years) % {"count": years}
    return ngettext("%(count)s day", "%(count)s days", days) % {"count": days}
