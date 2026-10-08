"""Texts for the test screen: intervals in Czech."""

from datetime import timedelta


def czech_plural(count, one, few, many):
    """Czech has three forms: 1 den, 2-4 dny, 5+ dní."""
    if count == 1:
        return one
    if 2 <= count <= 4:
        return few
    return many


def format_interval(interval):
    """Short text for an interval, e.g. "10 min", "5 h", "1 den", "8 dní", "1 rok".

    UI is only Czech for now; with more languages this needs translation catalogs.
    """
    if interval < timedelta(hours=1):
        minutes = max(1, round(interval / timedelta(minutes=1)))
        return f"{minutes} min"
    if interval < timedelta(days=1):
        hours = round(interval / timedelta(hours=1))
        return f"{hours} h"
    days = round(interval / timedelta(days=1))
    if days % 365 == 0:
        years = days // 365
        return f"{years} {czech_plural(years, 'rok', 'roky', 'let')}"
    return f"{days} {czech_plural(days, 'den', 'dny', 'dní')}"
