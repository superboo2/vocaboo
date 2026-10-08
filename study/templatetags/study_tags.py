from datetime import timedelta

from django import template
from django.utils import timezone

from ..formatting import format_interval

register = template.Library()


@register.filter
def interval(value):
    """{{ some_timedelta|interval }} -> "7 dní"."""
    return format_interval(value)


@register.filter
def due_text(due_at):
    """When a card comes back: "nové", "teď" or e.g. "za 3 dny"."""
    if due_at is None:
        return "nové"
    left = due_at - timezone.now()
    if left <= timedelta(0):
        return "teď"
    return f"za {format_interval(left)}"


@register.filter
def seconds(milliseconds):
    """1530 -> "1,5 s" (Czech decimal comma)."""
    if milliseconds is None:
        return ""
    return f"{milliseconds / 1000:.1f} s".replace(".", ",")
