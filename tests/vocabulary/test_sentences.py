"""The word inside a sentence: found automatically or marked with braces."""

import pytest
from django.template import Context, Template

from vocabulary.sentences import cloze, has_word, highlight, plain, split_sentence

GAP = '<span class="cloze" aria-label="vynechané slovo">___</span>'


def test_word_is_found_ignoring_case():
    assert highlight("Palm trees. She read my palm.", ["palm"]) == (
        "<mark>Palm</mark> trees. She read my <mark>palm</mark>."
    )


def test_only_whole_words_are_found():
    assert highlight("palmtree", ["palm"]) == "palmtree"
    assert not has_word("She has small palms.", ["palm"])


def test_longer_variant_wins():
    assert highlight("hello there", ["hell", "hello"]) == "<mark>hello</mark> there"


def test_any_variant_is_found():
    assert highlight("Hi, Ted!", ["hello", "hi"]) == "<mark>Hi</mark>, Ted!"


def test_html_is_escaped():
    assert highlight("<b>hi</b> & hello", ["hello"]) == (
        "&lt;b&gt;hi&lt;/b&gt; &amp; <mark>hello</mark>"
    )


def test_braces_mark_another_form():
    assert split_sentence("He {ran} away.", ["run"]) == [
        ("He ", False),
        ("ran", True),
        (" away.", False),
    ]
    assert highlight("He {ran} away.", ["run"]) == "He <mark>ran</mark> away."
    assert plain("He {ran} away.", ["run"]) == "He ran away."


def test_braces_win_over_automatic_search():
    # Only the marked "palms" counts, the other "palm" is plain text
    assert highlight("A palm with {palms}.", ["palm"]) == "A palm with <mark>palms</mark>."


def test_empty_braces_mean_the_main_variant():
    assert plain("She read my {}.", ["palm", "hand"]) == "She read my palm."


@pytest.mark.parametrize(
    ("sentence", "words", "expected"),
    [
        ("She can read from her palm.", ["palm"], f"She can read from her {GAP}."),
        ("He {ran} away.", ["run"], f"He {GAP} away."),
        ("Hello, hello!", ["hello"], f"{GAP}, {GAP}!"),
    ],
)
def test_cloze(sentence, words, expected):
    assert cloze(sentence, words) == expected


def test_cloze_escapes_html():
    assert cloze("<i>my palm</i>", ["palm"]) == f"&lt;i&gt;my {GAP}&lt;/i&gt;"


def test_template_filter():
    template = Template("{% load vocabulary_tags %}{{ s|marked_sentence:words }}")

    html = template.render(Context({"s": "He {ran} <away>", "words": ["run"]}))

    assert html == "He <mark>ran</mark> &lt;away&gt;"
