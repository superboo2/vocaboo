"""Texts for the test screen: intervals in Czech and marked words in sentences."""

import re
from datetime import timedelta

from django.utils.html import escape
from django.utils.safestring import mark_safe


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


def highlight(sentence, words):
    """Escape the sentence and wrap the given words in <mark>, ignoring letter case.

    Only whole words are marked: "palm" is marked in "my palm." but not in "palmtree".
    """
    words = sorted({word for word in words if word}, key=len, reverse=True)
    if not words:
        return escape(sentence)
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(word) for word in words) + r")(?!\w)",
        re.IGNORECASE,
    )
    parts = []
    last = 0
    for match in pattern.finditer(sentence):
        parts.append(escape(sentence[last : match.start()]))
        parts.append(f"<mark>{escape(match.group(0))}</mark>")
        last = match.end()
    parts.append(escape(sentence[last:]))
    return mark_safe("".join(parts))
