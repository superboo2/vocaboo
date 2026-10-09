"""Duplicate check (spec 5.1) and actions offered for it."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from vocabulary import services
from vocabulary.models import DeckTerm, Term


@pytest.fixture
def english(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


@pytest.fixture
def himym(english):
    return services.create_deck(english.owner, "HIMYM", parent=english)


@pytest.fixture
def bbt(english):
    return services.create_deck(english.owner, "Big Bang Theory", parent=english)


@pytest.fixture
def hello(himym):
    return services.add_term(himym, foreign="hello", native="ahoj; čau").term


def words(matches):
    return [match.term.main_foreign for match in matches]


# find_duplicates


def test_nothing_typed_gives_empty_check(himym, hello):
    check = services.find_duplicates(himym, foreign="", native="")

    assert not check
    assert not check.blocks


def test_new_word_has_no_duplicates(himym, hello):
    assert not services.find_duplicates(himym, foreign="legendary", native="legendární")


def test_same_word_in_other_deck(bbt, hello):
    check = services.find_duplicates(bbt, foreign="Hello", native="ahoj")

    assert check.exact.term == hello
    assert check.exact.deck_names == ["HIMYM"]
    assert check.exact.in_deck is None
    assert check.blocks


def test_same_word_in_this_deck(himym, hello):
    check = services.find_duplicates(himym, foreign="hello", native="ahoj")

    assert check.exact.in_deck is not None


def test_new_variants_are_found(bbt, hello):
    check = services.find_duplicates(bbt, foreign="hello; hi", native="ahoj; nazdar")

    assert check.exact.new_foreign == ["hi"]
    assert check.exact.new_native == ["nazdar"]


def test_match_on_other_foreign_variant(bbt, himym):
    services.add_term(himym, foreign="hello; hi", native="ahoj")

    check = services.find_duplicates(bbt, foreign="hi", native="čau")

    assert check.exact is None
    assert words(check.foreign) == ["hello"]
    assert not check.blocks


def test_match_only_on_translation(bbt, hello):
    # "hi → ahoj": "ahoj" is already the translation of "hello"
    check = services.find_duplicates(bbt, foreign="hi", native="ahoj")

    assert check.exact is None
    assert check.foreign == []
    assert words(check.native) == ["hello"]
    assert check.native[0].new_foreign == ["hi"]


def test_similar_without_accents(bbt, hello):
    check = services.find_duplicates(bbt, foreign="bye", native="cau")

    assert words(check.similar) == ["hello"]
    assert check.native == []


def test_diacritics_make_a_different_word(user, cs, es):
    # byt (flat) and být (to be) are different words, only "similar"
    deck = services.create_deck(user, "Čeština", foreign_language=cs, native_language=es)
    services.add_term(deck, foreign="být", native="ser")

    check = services.find_duplicates(deck, foreign="byt", native="piso")

    assert check.exact is None
    assert words(check.similar) == ["být"]


def test_other_users_words_are_ignored(other_user, en, cs, hello):
    deck = services.create_deck(other_user, "English", foreign_language=en, native_language=cs)

    assert not services.find_duplicates(deck, foreign="hello", native="ahoj")


def test_same_word_with_other_translation_is_another_meaning(himym):
    palm = services.add_term(himym, foreign="palm", native="dlaň").term

    check = services.find_duplicates(himym, foreign="palm", native="palma")

    assert check.exact is None
    assert [match.term for match in check.meanings] == [palm]
    assert not check.blocks


def test_same_word_before_the_translation_is_typed(himym):
    palm = services.add_term(himym, foreign="palm", native="dlaň").term

    check = services.find_duplicates(himym, foreign="palm", native="")

    assert [match.term for match in check.meanings] == [palm]
    assert not check.blocks


# Homonyms when saving


def test_other_meaning_is_saved_as_another_word(himym):
    services.add_term(himym, foreign="palm", native="dlaň")
    services.add_term(himym, foreign="palm", native="palma")

    assert sorted(Term.objects.values_list("main_native", flat=True)) == ["dlaň", "palma"]


def test_same_word_and_translation_is_refused(himym):
    services.add_term(himym, foreign="palm", native="dlaň")

    with pytest.raises(ValidationError) as error:
        services.add_term(himym, foreign="Palm", native="Dlaň")

    assert "palm → dlaň" in error.value.message_dict["foreign"][0]


def test_update_cannot_make_a_copy_of_other_meaning(himym):
    services.add_term(himym, foreign="palm", native="dlaň")
    tree = services.add_term(himym, foreign="palm", native="palma").term

    with pytest.raises(ValidationError):
        services.update_term(tree, foreign="palm", native="dlaň")


# link_term


def test_link_word_to_other_deck(bbt, hello):
    deck_term, added = services.link_term(
        bbt, hello, foreign="hello", context_sentence="Hello, Penny."
    )

    assert deck_term.deck == bbt
    assert deck_term.context_sentence == "Hello, Penny."
    assert added == []
    assert Term.objects.count() == 1
    assert DeckTerm.objects.filter(term=hello).count() == 2


def test_link_adds_new_variants_at_the_end(bbt, hello):
    _deck_term, added = services.link_term(bbt, hello, foreign="Hello; hi", native="ahoj; nazdar")

    hello = Term.objects.prefetch_related("variants").get(pk=hello.pk)
    assert added == ["hi", "nazdar"]
    assert hello.foreign_variants == ["hello", "hi"]
    assert hello.native_variants == ["ahoj", "čau", "nazdar"]
    assert hello.main_foreign == "hello"


def test_link_to_deck_where_word_already_is(himym, hello):
    deck_term, added = services.link_term(himym, hello, foreign="hi")

    assert added == ["hi"]
    assert DeckTerm.objects.filter(term=hello).count() == 1
    assert deck_term.deck == himym


def test_link_needs_same_language_pair(user, es, cs, hello):
    spanish = services.create_deck(user, "Španělština", foreign_language=es, native_language=cs)

    with pytest.raises(ValidationError):
        services.link_term(spanish, hello)


# Views


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


def check(client, deck, **data):
    url = reverse("vocabulary:term_check", args=[deck.pk])
    return client.post(url, data, headers={"HX-Request": "true"}).content.decode()


def test_check_panel_offers_add_here(logged_client, bbt, hello):
    html = check(logged_client, bbt, foreign="hello; hi", native="ahoj")

    assert "už máš v: HIMYM" in html
    assert "Přidat i sem" in html
    assert "(+ hi)" in html
    assert "disabled" in html


def test_check_panel_for_word_already_in_deck(logged_client, himym, hello):
    html = check(logged_client, himym, foreign="hello", native="ahoj")

    assert "už v tomto slovníku je" in html
    assert "disabled" in html


def test_check_panel_offers_variant(logged_client, bbt, hello):
    html = check(logged_client, bbt, foreign="hi", native="ahoj")

    assert "jako překlad slova" in html
    assert "jako variantu k" in html
    assert "disabled" not in html


def test_check_panel_shows_similar(logged_client, bbt, hello):
    html = check(logged_client, bbt, foreign="bye", native="cau")

    assert "Podobné (bez diakritiky)" in html


def test_check_panel_shows_other_translation(logged_client, himym):
    services.add_term(himym, foreign="palm", native="dlaň")

    html = check(logged_client, himym, foreign="palm", native="palma")

    assert "už máš s jiným překladem" in html
    assert "Stejný význam: přidat jako variantu" in html
    assert "bude to další význam" in html
    assert "disabled" not in html


def test_check_panel_is_empty_for_new_word(logged_client, himym, hello):
    html = check(logged_client, himym, foreign="legendary", native="legendární")

    assert "term-check" in html  # the wrapper is always there
    assert 'class="term-check"' not in html


def test_link_view_adds_word_and_returns_form(logged_client, bbt, hello):
    url = reverse("vocabulary:term_link", args=[bbt.pk, hello.pk])

    response = logged_client.post(
        url, {"foreign": "hello; hi", "native": "ahoj"}, headers={"HX-Request": "true"}
    )
    html = response.content.decode()

    assert DeckTerm.objects.filter(deck=bbt, term=hello).exists()
    assert "Přidáno do „Big Bang Theory“: hello" in html
    assert "(+ hi)" in html
    assert 'hx-swap-oob="true"' in html


def test_link_view_rejects_other_users_word(client, other_user, en, cs, hello):
    client.force_login(other_user)
    deck = services.create_deck(other_user, "English", foreign_language=en, native_language=cs)

    url = reverse("vocabulary:term_link", args=[deck.pk, hello.pk])
    assert client.post(url, {}).status_code == 404


def test_add_view_saves_other_meaning(logged_client, himym):
    services.add_term(himym, foreign="palm", native="dlaň")

    logged_client.post(
        reverse("vocabulary:term_add", args=[himym.pk]),
        {"foreign": "palm", "native": "palma"},
        headers={"HX-Request": "true"},
    )

    assert Term.objects.filter(main_foreign="palm").count() == 2


def test_add_view_error_shows_duplicate_panel(logged_client, bbt, hello):
    response = logged_client.post(
        reverse("vocabulary:term_add", args=[bbt.pk]),
        {"foreign": "hello", "native": "ahoj"},
        headers={"HX-Request": "true"},
    )

    assert "Přidat i sem" in response.content.decode()
