from django import template

from .. import sentences

register = template.Library()


@register.filter
def marked_sentence(sentence, words):
    """{{ item.context_sentence|marked_sentence:term.foreign_variants }} -> HTML with <mark>."""
    return sentences.highlight(sentence, words)
