import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from study.models import ReviewState
from vocabulary import services
from vocabulary.models import DeckTerm


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def english(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


@pytest.fixture
def s01(user, english):
    return services.create_deck(user, "S01", parent=english)


@pytest.fixture
def e01(user, s01):
    return services.create_deck(user, "E01", parent=s01)


@pytest.fixture
def spanish(user, es, cs):
    return services.create_deck(user, "Španělština", foreign_language=es, native_language=cs)


def move_url(deck):
    return reverse("vocabulary:terms_move", args=[deck.pk])


# Service


def test_move_keeps_sentence_and_progress(s01, e01):
    deck_term = services.add_term(s01, foreign="hello", native="ahoj", context_sentence="Hello!")
    states = set(ReviewState.objects.values_list("pk", flat=True))

    assert services.move_deck_terms([deck_term], e01) == (1, 0)

    deck_term.refresh_from_db()
    assert deck_term.deck == e01
    assert deck_term.context_sentence == "Hello!"
    assert set(ReviewState.objects.values_list("pk", flat=True)) == states


def test_copy_leaves_word_in_both_decks(s01, e01):
    deck_term = services.add_term(s01, foreign="hello", native="ahoj", context_sentence="Hello!")

    services.move_deck_terms([deck_term], e01, copy=True)

    copied = DeckTerm.objects.get(deck=e01)
    assert copied.term == deck_term.term
    assert copied.context_sentence == "Hello!"
    assert DeckTerm.objects.filter(deck=s01).count() == 1


def test_move_to_deck_that_has_the_word(s01, e01):
    deck_term = services.add_term(s01, foreign="hello", native="ahoj", context_sentence="Hello!")
    services.link_term(e01, deck_term.term)

    assert services.move_deck_terms([deck_term], e01) == (1, 1)

    # Not doubled; the target gets the sentence it did not have
    assert DeckTerm.objects.filter(term=deck_term.term).count() == 1
    assert DeckTerm.objects.get(term=deck_term.term).deck == e01
    assert DeckTerm.objects.get(term=deck_term.term).context_sentence == "Hello!"


def test_move_to_other_languages_is_refused(s01, spanish):
    deck_term = services.add_term(s01, foreign="hello", native="ahoj")

    with pytest.raises(ValidationError):
        services.move_deck_terms([deck_term], spanish)
    assert DeckTerm.objects.get().deck == s01


def test_move_targets_have_same_languages(s01, e01, english, spanish):
    targets = [deck for deck, _path in services.get_term_move_targets(s01)]

    assert targets == [english, e01]


# Views


def test_move_page_lists_chosen_words(logged_client, s01, e01):
    hello = services.add_term(s01, foreign="hello", native="ahoj")
    services.add_term(s01, foreign="bye", native="nashle")

    html = logged_client.get(move_url(s01), {"ids": [hello.pk]}).content.decode()

    assert "hello" in html
    assert "bye" not in html
    assert "Angličtina › S01 › E01" in html


def test_move_page_without_words_goes_back(logged_client, s01):
    response = logged_client.get(move_url(s01))

    assert response.status_code == 302
    assert response.url == reverse("vocabulary:deck_detail", args=[s01.pk])


def test_move_words_by_post(logged_client, s01, e01):
    hello = services.add_term(s01, foreign="hello", native="ahoj")
    bye = services.add_term(s01, foreign="bye", native="nashle")

    response = logged_client.post(
        move_url(s01), {"ids": [hello.pk, bye.pk], "target": e01.pk, "action": "move"}, follow=True
    )

    assert set(DeckTerm.objects.values_list("deck", flat=True)) == {e01.pk}
    assert "Přesunuto do „E01“: 2 slovíčka." in response.content.decode()


def test_copy_words_by_post(logged_client, s01, e01):
    hello = services.add_term(s01, foreign="hello", native="ahoj")

    logged_client.post(move_url(s01), {"ids": [hello.pk], "target": e01.pk, "action": "copy"})

    assert DeckTerm.objects.filter(term=hello.term).count() == 2


def test_words_of_other_deck_are_ignored(logged_client, s01, e01):
    in_e01 = services.add_term(e01, foreign="hello", native="ahoj")

    response = logged_client.get(move_url(s01), {"ids": [in_e01.pk]})

    assert response.status_code == 302


def test_other_users_deck_gives_404(client, other_user, s01):
    client.force_login(other_user)

    assert client.get(move_url(s01), {"ids": [1]}).status_code == 404


def test_deck_page_has_selection(logged_client, s01):
    services.add_term(s01, foreign="hello", native="ahoj")

    html = logged_client.get(reverse("vocabulary:deck_detail", args=[s01.pk])).content.decode()

    assert 'class="select-box"' in html
    assert move_url(s01) in html
