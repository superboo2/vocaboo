"""The word inside a sentence: find it, mark it, or leave a gap for it.

The user writes a normal sentence ("She can read from her palm.") and the word is found
automatically. A different form of the word can be marked with braces:
"He {ran} away." for the word "run". Empty braces "{}" mean the main variant of the word.
"""

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

BRACES = re.compile(r"\{([^{}]*)\}")
GAP_HTML = '<span class="cloze" aria-label="vynechané slovo">___</span>'


def split_sentence(sentence, words):
    """Split the sentence into parts: list of (text, is_word).

    With braces only the marked parts are words. Without braces every whole word that
    equals one of the variants (letter case ignored) is a word: "palm" in "my palm." but
    not in "palmtree".
    """
    sentence = sentence or ""
    words = [word for word in words if word]
    if BRACES.search(sentence):
        parts = []
        last = 0
        for match in BRACES.finditer(sentence):
            parts.append((sentence[last : match.start()], False))
            parts.append((match.group(1).strip() or (words[0] if words else ""), True))
            last = match.end()
        parts.append((sentence[last:], False))
        return [part for part in parts if part[0]]

    if not words:
        return [(sentence, False)] if sentence else []
    # Longer variants first, so "hello" wins over "hell"
    alternatives = "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))
    pattern = re.compile(r"(?<!\w)(" + alternatives + r")(?!\w)", re.IGNORECASE)
    parts = []
    last = 0
    for match in pattern.finditer(sentence):
        parts.append((sentence[last : match.start()], False))
        parts.append((match.group(0), True))
        last = match.end()
    parts.append((sentence[last:], False))
    return [part for part in parts if part[0]]


def has_word(sentence, words):
    """True when the word was found (or marked) in the sentence."""
    return any(is_word for _text, is_word in split_sentence(sentence, words))


def plain(sentence, words):
    """The sentence as text, without braces."""
    return "".join(text for text, _is_word in split_sentence(sentence, words))


def highlight(sentence, words):
    """HTML of the sentence with the word in <mark>; all text is escaped."""
    html = "".join(
        f"<mark>{escape(text)}</mark>" if is_word else escape(text)
        for text, is_word in split_sentence(sentence, words)
    )
    return mark_safe(html)


def cloze(sentence, words):
    """HTML of the sentence with a gap instead of the word (for the native → foreign card)."""
    html = "".join(
        GAP_HTML if is_word else escape(text) for text, is_word in split_sentence(sentence, words)
    )
    return mark_safe(html)
