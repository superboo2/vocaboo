"""Pronunciation of words from the dictionary: provider, card, word page, test page."""

import pytest
from django.urls import reverse

from dictionary.models import DictionaryEntry
from dictionary.providers import get_pronunciation
from study import services as study_services
from study.cards import build_card
from study.models import Direction, ReviewState
from vocabulary import services

AUDIO = "https://upload.wikimedia.org/En-us-palm.ogg.mp3"


def entry(word, part_of_speech, ipa="", audio_url="", foreign_code="en"):
    return DictionaryEntry.objects.create(
        source="cswiktionary",
        foreign_code=foreign_code,
        native_code="cs",
        word=word,
        part_of_speech=part_of_speech,
        senses=[{"text": "dlaň", "examples": []}],
        ipa=ipa,
        audio_url=audio_url,
    )


@pytest.fixture
def palm(db):
    # IPA in one entry, the recording in another one (it happens in Wiktionary)
    entry("palm", "podstatné jméno", ipa="[pɑːm]")
    entry("palm", "sloveso", audio_url=AUDIO)


@pytest.fixture
def deck(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


# Provider


def test_pronunciation_joins_ipa_and_recording(palm):
    result = get_pronunciation("Palm", "en")

    assert (result.ipa, result.audio_url, result.source_label) == ("pɑːm", AUDIO, "Wiktionary")


def test_pronunciation_uses_first_variant(palm):
    assert get_pronunciation("palm; palm tree", "en").ipa == "pɑːm"


def test_no_pronunciation_for_unknown_word_or_language(palm):
    assert get_pronunciation("suit up", "en") is None
    assert get_pronunciation("palm", "es") is None


def test_no_pronunciation_without_providers(palm, settings):
    settings.PRONUNCIATION_PROVIDERS = []

    assert get_pronunciation("palm", "en") is None


# Card


def card_for(user, deck, term, direction):
    session = study_services.start_session(user, [deck])
    state = ReviewState.objects.get(term=term, direction=direction)
    return build_card(session, state)


def test_card_has_recording_but_no_ipa_by_default(user, deck, palm):
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.N2F)

    assert card.pronunciation.audio_url == AUDIO
    assert card.pronunciation.ipa == ""
    assert card.sources_note == "(výslovnost z Wiktionary)"


def test_card_with_ipa_in_settings(user, deck, palm):
    user.show_ipa = True
    user.save()
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.N2F)

    assert card.pronunciation.ipa == "pɑːm"


def test_only_ipa_and_ipa_turned_off_gives_nothing(user, deck):
    entry("knight", "podstatné jméno", ipa="[naɪt]")
    term = services.add_term(deck, foreign="knight", native="rytíř").term

    card = card_for(user, deck, term, Direction.F2N)

    assert card.pronunciation is None
    # Only the other meaning from the dictionary is named, not the pronunciation
    assert card.sources_note == "(další významy z Wiktionary)"


def test_card_without_pronunciation_in_settings(user, deck, palm):
    user.show_pronunciation = False
    user.save()
    term = services.add_term(deck, foreign="palm", native="dlaň").term

    card = card_for(user, deck, term, Direction.F2N)

    assert card.pronunciation is None
    assert card.sources_note == ""


def test_test_page_has_play_button(client, user, deck, palm):
    user.autoplay_pronunciation = True
    user.save()
    services.add_term(deck, foreign="palm", native="dlaň")
    session = study_services.start_session(user, [deck])
    client.force_login(user)

    html = client.get(reverse("study:card", args=[session.pk])).content.decode()

    assert f'data-audio="{AUDIO}"' in html
    assert "pɑːm" not in html
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
    assert f'data-audio="{AUDIO}"' in html
    assert "Wikimedia Commons" in html
