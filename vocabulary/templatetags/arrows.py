"""Arrows of language pairs and translations (EN → CS, palm → dlaň) as small SVG icons; EN ⇄ CS
is a test in both directions.

The character → sits low next to capital letters and looks different in every font; the icon
is centred on capital letters and has the line of the other icons. Plain text (title, select,
page title) keeps the character.
"""

from django import template
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

register = template.Library()

ONE_WAY = '<path d="M1.5 8h12.5M10 4.5L14 8l-4 3.5"/>'
BOTH_WAYS = '<path d="M2 8h12M5.5 4.5L2 8l3.5 3.5M10.5 4.5L14 8l-3.5 3.5"/>'
# A test in both directions (EN ⇄ CS): an arrow there and under it an arrow back
THERE_AND_BACK = '<path d="M2 4.5h12M11.5 2L14 4.5L11.5 7M14 11.5H2M4.5 9L2 11.5L4.5 14"/>'


def _svg(both, label=None, path=None, title=None):
    # With a label screen readers say "EN to CS"; without it the arrow is only a picture
    if label:
        extra = format_html(' role="img" aria-label="{}"', label)
    else:
        extra = mark_safe(' aria-hidden="true"')
    return format_html(
        '<svg class="arrow" viewBox="0 0 16 16"{}>{}{}</svg>',
        extra,
        format_html("<title>{}</title>", title) if title else "",
        mark_safe(path or (BOTH_WAYS if both else ONE_WAY)),
    )


@register.simple_tag
def arrow(both=False):
    """{% arrow %} → or {% arrow both=True %} ↔ between two words."""
    return _svg(both)


@register.filter
def arrows(text):
    """{{ "EN → CS"|arrows }}: the arrows in a text become icons, the rest is escaped."""
    html = str(conditional_escape(text))
    for character, icon in (
        ("→", _svg(False, _("to"))),
        ("↔", _svg(True, _("and back"))),
        ("⇄", _svg(False, _("both directions"), THERE_AND_BACK, _("both directions"))),
    ):
        if character in html:
            icon = str(icon)
            html = html.replace(f" {character} ", icon).replace(character, icon)
    return mark_safe(html)
