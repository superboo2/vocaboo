from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from study.models import Direction, ReviewState

from . import services
from .models import DeckTerm, Term


@pytest.fixture
def english(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


@pytest.fixture
def himym(english):
    return services.create_deck(english.owner, "HIMYM", parent=english)


@pytest.fixture
def bbt(english):
    return services.create_deck(english.owner, "Big Bang Theory", parent=english)


# Cleaning input


def test_clean_text_trims_and_joins_spaces():
    assert services.clean_text("  hello   there \n") == "hello there"


def test_clean_text_unifies_unicode():
    # "c" + combining caron looks like "č" but is a different string
    decomposed = "čau"
    assert decomposed != "čau"
    assert services.clean_text(decomposed) == "čau"


def test_parse_variants():
    assert services.parse_variants("hello; hi") == ["hello", "hi"]
    assert services.parse_variants(" hello ;; hi ; ") == ["hello", "hi"]
    # Repeated variant (any letter case) is kept only once
    assert services.parse_variants("Hello; hello; HI; hi") == ["Hello", "HI"]
    assert services.parse_variants(" ; ") == []


# Adding


def test_add_term_creates_everything(himym):
    deck_term = services.add_term(
        himym,
        foreign="hello; hi",
        native="Ahoj; čau",
        context_sentence="Hello, kids.",
        context_source="S01E01",
    )

    term = deck_term.term
    assert term.main_foreign == "hello"
    assert term.foreign_variants == ["hello", "hi"]
    assert term.native_variants == ["Ahoj", "čau"]
    assert term.foreign_language == himym.foreign_language
    assert deck_term.deck == himym
    assert deck_term.context_sentence == "Hello, kids."
    assert deck_term.context_source == "S01E01"
    directions = set(ReviewState.objects.filter(term=term).values_list("direction", flat=True))
    assert directions == {Direction.F2N, Direction.N2F}
    assert ReviewState.objects.filter(term=term, due_at__isnull=False).count() == 0


def test_add_term_needs_both_sides(himym):
    with pytest.raises(ValidationError) as error:
        services.add_term(himym, foreign="hello", native=" ; ")

    assert "native" in error.value.message_dict
    assert not Term.objects.exists()


def test_add_term_rejects_too_long_variant(himym):
    with pytest.raises(ValidationError):
        services.add_term(himym, foreign="x" * 201, native="y")


def test_same_word_is_not_created_twice(himym, bbt):
    services.add_term(himym, foreign="hello", native="ahoj")

    with pytest.raises(ValidationError) as error:
        services.add_term(bbt, foreign="Hello", native="ahoj")

    assert "HIMYM" in error.value.message_dict["foreign"][0]
    assert Term.objects.count() == 1


def test_other_meaning_is_a_new_word(himym):
    services.add_term(himym, foreign="palm", native="dlaň", meaning_hint="ruka")
    services.add_term(himym, foreign="palm", native="palma", meaning_hint="strom")

    assert Term.objects.filter(main_foreign="palm").count() == 2


def test_same_text_in_other_language_pair_is_fine(himym, user, es, cs):
    spanish = services.create_deck(user, "Španělština", foreign_language=es, native_language=cs)
    services.add_term(himym, foreign="no", native="ne")
    services.add_term(spanish, foreign="no", native="ne")

    assert Term.objects.count() == 2


# Changing


def test_update_term_replaces_variants(himym):
    term = services.add_term(himym, foreign="hello", native="ahoj").term

    services.update_term(term, foreign="hi; hello", native="čau", note=" informal ")

    term = Term.objects.prefetch_related("variants").get(pk=term.pk)
    assert term.main_foreign == "hi"
    assert term.foreign_variants == ["hi", "hello"]
    assert term.native_variants == ["čau"]
    assert term.note == "informal"


def test_update_term_cannot_copy_other_word(himym):
    services.add_term(himym, foreign="hello", native="ahoj")
    term = services.add_term(himym, foreign="hi", native="čau").term

    with pytest.raises(ValidationError):
        services.update_term(term, foreign="Hello", native="čau")


def test_update_term_can_keep_its_own_text(himym):
    term = services.add_term(himym, foreign="hello", native="ahoj").term

    services.update_term(term, foreign="Hello", native="ahoj")

    term.refresh_from_db()
    assert term.main_foreign == "Hello"


def test_update_deck_term(himym):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")

    services.update_deck_term(deck_term, context_sentence=" Hi! ", context_source="S01E02")

    deck_term.refresh_from_db()
    assert (deck_term.context_sentence, deck_term.context_source) == ("Hi!", "S01E02")


# Removing


def test_remove_last_link_deletes_word(himym):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")
    assert services.term_is_only_in(deck_term)

    deleted = services.remove_term_from_deck(deck_term)

    assert deleted
    assert not Term.objects.exists()
    assert not ReviewState.objects.exists()


def test_remove_keeps_word_used_in_other_deck(himym, bbt):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")
    DeckTerm.objects.create(deck=bbt, term=deck_term.term)
    assert not services.term_is_only_in(deck_term)

    deleted = services.remove_term_from_deck(deck_term)

    assert not deleted
    assert Term.objects.count() == 1
    assert ReviewState.objects.count() == 2


def test_delete_deck_deletes_only_unused_words(english, himym, bbt):
    shared = services.add_term(himym, foreign="hello", native="ahoj").term
    DeckTerm.objects.create(deck=bbt, term=shared)
    services.add_term(himym, foreign="legendary", native="legendární")

    assert services.count_terms_deleted_with_deck(himym) == 1
    deck_count, term_count = services.delete_deck(himym)

    assert (deck_count, term_count) == (1, 1)
    assert list(Term.objects.values_list("main_foreign", flat=True)) == ["hello"]


def test_delete_deck_with_children_deletes_their_words(english, himym):
    services.add_term(himym, foreign="hello", native="ahoj")
    services.add_term(english, foreign="bye", native="nashle")

    assert services.count_terms_deleted_with_deck(english) == 2
    assert services.delete_deck(english) == (2, 2)
    assert not Term.objects.exists()


# Listing


def test_list_deck_terms_sorting(himym):
    services.add_term(himym, foreign="banana", native="banán")
    later = services.add_term(himym, foreign="apple", native="jablko")
    soon = services.add_term(himym, foreign="cherry", native="třešeň")
    now = timezone.now()
    ReviewState.objects.filter(term=later.term).update(due_at=now + timedelta(days=7))
    ReviewState.objects.filter(term=soon.term, direction=Direction.N2F).update(
        due_at=now + timedelta(days=1)
    )

    def words(sort):
        return [item.term.main_foreign for item in services.list_deck_terms(himym, sort)]

    assert words("added") == ["cherry", "apple", "banana"]
    assert words("alpha") == ["apple", "banana", "cherry"]
    # Earliest repetition first, never reviewed words last
    assert words("due") == ["cherry", "apple", "banana"]


def test_list_deck_terms_query_count(himym, django_assert_num_queries):
    for word in ["a", "b", "c"]:
        services.add_term(himym, foreign=word, native=word)

    with django_assert_num_queries(2):
        items = list(services.list_deck_terms(himym))
        texts = [item.term.foreign_variants for item in items]

    assert len(texts) == 3
