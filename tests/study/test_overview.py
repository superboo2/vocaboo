"""Dashboard numbers and the word page (spec 7.1, 8)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from study import services
from study.models import Direction, ReviewState
from study.templatetags.study_tags import due_text, seconds
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm


@pytest.fixture
def tree(user, en, cs):
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    series = vocabulary.create_deck(user, "Seriály", parent=english)
    return {
        "english": english,
        "series": series,
        "himym": vocabulary.create_deck(user, "HIMYM", parent=series),
        "bbt": vocabulary.create_deck(user, "Big Bang Theory", parent=series),
    }


def add(deck, word):
    return vocabulary.add_term(deck, foreign=word, native=word).term


def make_due(term):
    ReviewState.objects.filter(term=term, direction=Direction.F2N).update(
        due_at=timezone.now() - timedelta(hours=1)
    )


def make_later(term):
    ReviewState.objects.filter(term=term).update(due_at=timezone.now() + timedelta(days=5))


# Deck counts


def test_counts_include_children_and_count_shared_words_once(user, tree):
    hello = add(tree["himym"], "hello")
    DeckTerm.objects.create(deck=tree["bbt"], term=hello)
    add(tree["bbt"], "physics")
    add(tree["english"], "general")

    roots = vocabulary.load_tree(user)
    totals = services.annotate_deck_counts(roots, user)

    english = roots[0]
    series = english.tree_children[0]
    himym, bbt = series.tree_children
    assert (english.word_count, series.word_count, himym.word_count, bbt.word_count) == (3, 2, 1, 2)
    assert totals == {"words": 3, "due": 0, "new": 3}


def test_due_and_new_counts(user, tree):
    due = add(tree["himym"], "due")
    later = add(tree["himym"], "later")
    add(tree["himym"], "new")
    make_due(due)
    make_later(later)

    roots = vocabulary.load_tree(user)
    totals = services.annotate_deck_counts(roots, user)

    assert totals == {"words": 3, "due": 1, "new": 1}
    himym = roots[0].tree_children[0].tree_children[0]
    assert (himym.due_count, himym.new_count) == (1, 1)


def test_counts_use_few_queries(user, tree, django_assert_max_num_queries):
    for word in ["a", "b", "c", "d"]:
        add(tree["himym"], word)
    roots = vocabulary.load_tree(user)

    with django_assert_max_num_queries(3):
        services.annotate_deck_counts(roots, user)


def test_dashboard_shows_counts(client, user, tree):
    due = add(tree["himym"], "due")
    add(tree["himym"], "new")
    make_due(due)
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    # The words to review are on the button, the count of words after the deck name
    assert "Spustit test · 1 k opakování" in html
    # All words and the known ones next to the heading
    assert "2 slovíčka (+2 dnes)" in html
    assert "0 umíš" in html
    assert "Teď k opakování" not in html
    assert '<small class="deck-counts">(2 <span class="deck-due" title="1 k opakování">' in html
    assert '<span aria-hidden="true">↻</span> 1<span' in html


# Word history


def test_term_history(user, tree):
    hello = add(tree["himym"], "hello")
    session = services.start_session(user, [tree["himym"]])
    # The order of the directions is random
    first = services.next_card(session)
    services.record_answer(session, first, "ok")
    services.record_answer(session, services.next_card(session), "dontknow")

    history = services.term_history(hello)

    by_direction = {row["direction"]: row for row in history["directions"]}
    assert by_direction["F2N"]["total"] == 1
    assert by_direction["N2F"]["total"] == 1
    assert dict((r.key, c) for r, c in by_direction[first.direction]["counts"])["ok"] == 1
    assert [log.rating for log in history["logs"]] == ["dontknow", "ok"]


def test_word_page(client, user, tree):
    item = vocabulary.add_term(
        tree["himym"], foreign="hello; hi", native="ahoj", context_sentence="Hello, kids."
    )
    DeckTerm.objects.create(deck=tree["bbt"], term=item.term, context_sentence="Hello, Penny.")
    session = services.start_session(user, [tree["himym"]], direction="F2N")
    services.record_answer(session, services.next_card(session), "think", think_ms=2400)
    client.force_login(user)

    url = reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk])
    html = client.get(url).content.decode()

    assert "hello · hi" in html
    assert "Big Bang Theory" in html and "<mark>Hello</mark>, Penny." in html
    assert "Vím po zamyšlení" in html
    assert "2,4 s" in html
    assert "za 3 dny" in html
    assert "nové" in html  # the N2F direction was never reviewed


def test_word_list_links_to_word_page(client, user, tree):
    item = vocabulary.add_term(tree["himym"], foreign="hello", native="ahoj")
    client.force_login(user)

    html = client.get(reverse("vocabulary:deck_detail", args=[tree["himym"].pk])).content.decode()

    assert reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk]) in html


def test_word_page_of_other_user_gives_404(client, other_user, tree):
    item = vocabulary.add_term(tree["himym"], foreign="hello", native="ahoj")
    client.force_login(other_user)

    url = reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk])
    assert client.get(url).status_code == 404


# Filters


def test_due_text():
    now = timezone.now()

    assert due_text(None) == "nové"
    assert due_text(now - timedelta(minutes=1)) == "teď"
    assert due_text(now + timedelta(days=3, minutes=1)) == "za 3 dny"


def test_seconds():
    assert seconds(1530) == "1,5 s"
    assert seconds(None) == ""
