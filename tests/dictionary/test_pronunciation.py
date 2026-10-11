"""Pronunciation of words: IPA from the dictionary of the app, sound from the browser."""

import pytest
from django.urls import reverse

from dictionary.providers import get_pronunciation
from study import services as study_services
from study.cards import build_card
from study.models import Direction, ReviewState
from tests.conftest import lexicon_entry
from vocabulary import services


@pytest.fixture
def palm(lexicon):
    # The IPA of the more common entry wins
    lexicon(
        lexicon_entry(
            "palm",
            "verb",
            [("podstrčit", "He {palmed} the card.", "Kartu {podstrčil}.")],
            band=9,
            ipa="pɑːmd",
        ),
        lexicon_entry(
            "palm",
            "noun",
            [("dlaň", "She read my {palm}.", "Četla mi z {dlaně}.")],
            band=5,
            ipa="pɑːm",
        ),
    )


@pytest.fixture
def deck(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


# Provider


def test_pronunciation_from_the_dictionary(palm):
    assert get_pronunciation("Palm", "en").ipa == "pɑːm"
    assert get_pronunciation("palm; palm tree", "en").ipa == "pɑːm"


def test_no_pronunciation(palm, settings):
    assert get_pronunciation("suit up", "en") is None
    assert get_pronunciation("palm", "es") is None
    # The user does not want to see IPA
    assert get_pronunciation("palm", "en", with_ipa=False) is None
    settings.PRONUNCIATION_PROVIDERS = []
    assert get_pronunciation("palm", "en") is None


# Card


def card_for(user, deck, term, direction):
    session = study_services.start_session(user, [deck])
    state = ReviewState.objects.get(term=term, direction=direction)
    return build_card(session, state)


def test_card_has_no_ipa_by_default(user, deck, palm):
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.N2F)

    assert card.pronunciation is None
    assert card.speech_lang == "en"


def test_card_with_ipa_in_settings(user, deck, palm):
    user.show_ipa = True
    user.save()
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.N2F)

    assert card.pronunciation.ipa == "pɑːm"


def test_card_without_pronunciation_in_settings(user, deck, palm):
    user.show_pronunciation = False
    user.show_ipa = True
    user.save()
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.F2N)

    assert card.pronunciation is None
    assert card.speech_lang == ""


def test_test_page_has_play_button(client, user, deck, palm):
    user.autoplay_pronunciation = True
    user.save()
    services.add_term(deck, foreign="palm", native="dlaň")
    session = study_services.start_session(user, [deck])
    client.force_login(user)

    html = client.get(reverse("study:card", args=[session.pk])).content.decode()

    assert 'data-speak-text="palm" data-lang="en"' in html
    assert "data-audio" not in html
    assert "data-autoplay" in html


# Word page


def test_word_page_shows_pronunciation(client, user, deck, palm):
    user.show_ipa = True
    user.save()
    deck_term = services.add_term(deck, foreign="palm", native="dlaň")
    client.force_login(user)

    url = reverse("vocabulary:term_detail", args=[deck.pk, deck_term.pk])
    html = client.get(url).content.decode()

    assert "[pɑːm]" in html
    assert 'data-speak-text="palm"' in html
    assert "Wiktionary" not in html


# Voice of the browser


def test_card_can_be_read_by_the_browser(client, user, deck):
    services.add_term(deck, foreign="suit up", native="obléct se", context_sentence="{Suit up}!")
    session = study_services.start_session(user, [deck], direction="F2N")
    client.force_login(user)

    html = client.get(reverse("study:card", args=[session.pk])).content.decode()

    # Word and sentence, both for the browser voice (hidden until it has a voice for "en")
    assert 'data-speak="word"' in html
    assert 'data-speak-text="suit up" data-lang="en" hidden' in html
    assert 'data-speak="sentence"' in html
    assert 'data-speak-text="Suit up!"' in html


def test_card_text_for_reading(user, deck):
    term = services.add_term(
        deck, foreign="run", native="běžet", context_sentence="He {ran} away."
    ).term

    card = card_for(user, deck, term, Direction.N2F)

    assert card.speech_lang == "en"
    assert card.sentence_text == "He ran away."


def test_no_voice_when_pronunciation_is_off(client, user, deck):
    user.show_pronunciation = False
    user.save()
    services.add_term(deck, foreign="suit up", native="obléct se", context_sentence="Suit up!")
    session = study_services.start_session(user, [deck])
    client.force_login(user)

    html = client.get(reverse("study:card", args=[session.pk])).content.decode()

    assert "data-speak" not in html


def test_word_page_can_read_sentences(client, user, deck):
    deck_term = services.add_term(
        deck, foreign="run", native="běžet", context_sentence="He {ran} away."
    )
    client.force_login(user)

    url = reverse("vocabulary:term_detail", args=[deck.pk, deck_term.pk])
    html = client.get(url).content.decode()

    assert 'data-speak-text="run"' in html
    assert 'data-speak-text="He ran away."' in html
