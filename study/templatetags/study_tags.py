from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from ..formatting import format_interval

register = template.Library()


@register.filter
def interval(value):
    """{{ some_timedelta|interval }} -> "7 days"."""
    return format_interval(value)


@register.filter
def due_text(due_at):
    """When a card comes back: "new", "now" or e.g. "in 3 days"."""
    if due_at is None:
        return pgettext("due", "new")
    left = due_at - timezone.now()
    if left <= timedelta(0):
        return pgettext("due", "now")
    return _("in %(interval)s") % {"interval": format_interval(left)}


@register.filter
def seconds(milliseconds):
    """1530 -> "1.5 s" ("1,5 s" in Czech, the decimal mark of the language)."""
    if milliseconds is None:
        return ""
    return _("%(seconds)s s") % {"seconds": number_format(milliseconds / 1000, decimal_pos=1)}
