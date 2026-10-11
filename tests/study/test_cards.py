"""Texts on the card (formatting, marked words) and what a card shows (spec 6.4)."""

from datetime import timedelta

import pytest

from study import services
from study.cards import build_card
from study.formatting import format_interval
from study.models import Direction, ReviewState, StudyDirection
from tests.conftest import lexicon_entry
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm

# Formatting


@pytest.mark.parametrize(
    ("interval", "text"),
    [
        (timedelta(minutes=10), "10 min"),
        (timedelta(seconds=20), "1 min"),
        (timedelta(hours=5), "5 h"),
        (timedelta(days=1), "1 den"),
        (timedelta(days=3), "3 dny"),
        (timedelta(days=4), "4 dny"),
        (timedelta(days=8), "8 dní"),
        (timedelta(days=280), "280 dní"),
        (timedelta(days=365), "1 rok"),
        (timedelta(days=730), "2 roky"),
    ],
)
def test_format_interval(interval, text):
    assert format_interval(interval) == text


# Cards


@pytest.fixture
def decks(user, en, cs):
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    return {
        "english": english,
        "himym": vocabulary.create_deck(user, "HIMYM", parent=english),
        "bbt": vocabulary.create_deck(user, "Big Bang Theory", parent=english),
    }


def card_for(user, deck, term, direction):
    session = services.start_session(user, [deck])
    state = (
        ReviewState.objects.select_related("term")
        .prefetch_related("term__variants")
        .get(term=term, direction=direction)
    )
    return build_card(session, state)


def test_f2n_card(user, decks):
    term = vocabulary.add_term(
        decks["himym"], foreign="hello; hi", native="ahoj; čau", context_sentence="Hello, kids."
    ).term

    card = card_for(user, decks["himym"], term, Direction.F2N)

    assert card.question == ["hello", "hi"]
    assert card.answer == ["ahoj", "čau"]
    assert card.sentence_on_front
    assert card.sentence == "<mark>Hello</mark>, kids."
    assert [rating.key for rating, _ in card.preview] == ["ok", "think", "partial", "dontknow"]


def test_n2f_card_has_gap_on_front_and_sentence_on_back(user, decks):
    sentence = "She can read from her palm."
    term = vocabulary.add_term(
        decks["himym"], foreign="palm", native="dlaň", context_sentence=sentence
    ).term

    card = card_for(user, decks["himym"], term, Direction.N2F)

    assert card.question == ["dlaň"]
    assert card.answer == ["palm"]
    assert not card.sentence_on_front
    assert "palm" not in card.cloze
    assert "___" in card.cloze
    assert card.sentence == "She can read from her <mark>palm</mark>."


def test_n2f_card_with_marked_other_form(user, decks):
    term = vocabulary.add_term(
        decks["himym"], foreign="run", native="běžet", context_sentence="He {ran} away."
    ).term

    card = card_for(user, decks["himym"], term, Direction.N2F)

    assert "ran" not in card.cloze
    assert card.sentence == "He <mark>ran</mark> away."


def test_n2f_card_without_found_word_keeps_sentence_only_on_back(user, decks):
    # "palms" is another form and is not marked: a gap cannot be made, the answer must not show
    term = vocabulary.add_term(
        decks["himym"], foreign="palm", native="dlaň", context_sentence="She has small palms."
    ).term

    card = card_for(user, decks["himym"], term, Direction.N2F)

    assert card.cloze == ""
    assert card.sentence == "She has small palms."


def test_sentence_from_other_deck_of_the_test(user, decks):
    term = vocabulary.add_term(decks["himym"], foreign="hello", native="ahoj").term
    DeckTerm.objects.create(deck=decks["bbt"], term=term, context_sentence="Hello, Penny.")

    card = card_for(user, decks["english"], term, Direction.F2N)

    assert "Penny" in card.sentence


def test_sentence_changes_between_reviews(user, decks):
    term = vocabulary.add_term(
        decks["himym"], foreign="hello", native="ahoj", context_sentence="Hello, kids."
    ).term
    DeckTerm.objects.create(deck=decks["bbt"], term=term, context_sentence="Hello, Penny.")

    first = card_for(user, decks["english"], term, Direction.F2N).sentence
    ReviewState.objects.filter(term=term, direction=Direction.F2N).update(reviews_count=1)
    second = card_for(user, decks["english"], term, Direction.F2N).sentence

    assert first != second


def test_homonym_without_sentence_gets_hint(user, decks):
    tree = vocabulary.add_term(decks["himym"], foreign="palm", native="palma").term
    vocabulary.add_term(decks["himym"], foreign="palm", native="dlaň")

    card = card_for(user, decks["himym"], tree, Direction.F2N)

    assert card.front_hint == "2 významy"
    assert card.own_meanings == [["dlaň"]]


def test_homonym_with_sentence_needs_no_hint(user, decks):
    hand = vocabulary.add_term(
        decks["himym"], foreign="palm", native="dlaň", context_sentence="She read my palm."
    ).term
    vocabulary.add_term(decks["himym"], foreign="palm", native="palma")

    card = card_for(user, decks["himym"], hand, Direction.F2N)

    assert card.front_hint == ""
    assert card.own_meanings == [["palma"]]


def test_other_meanings_come_also_from_the_dictionary(user, decks, lexicon):
    lexicon(
        lexicon_entry(
            "present",
            "noun",
            [
                ("dárek", "A {present}.", "{Dárek}."),
                ("současnost", "The {present}.", "{Současnost}."),
            ],
        )
    )
    gift = vocabulary.add_term(decks["himym"], foreign="present", native="dárek").term

    card = card_for(user, decks["himym"], gift, Direction.F2N)

    # The word's own meaning is not repeated; the dictionary one is not "own"
    assert card.own_meanings == []
    assert card.dictionary_meanings == ["současnost"]
    # Meanings from the dictionary do not make the front ambiguous
    assert card.front_hint == ""


@pytest.fixture
def light_entry(lexicon):
    senses = ["světlo", "lehký", "světlý", "dietní", "zapálit", "osvětlit"]
    lexicon(lexicon_entry("light", "noun", [(text, "{Light}.", text) for text in senses]))


def test_card_has_all_dictionary_meanings(user, decks, light_entry):
    vocabulary.add_term(decks["himym"], foreign="light", native="lehký")
    term = vocabulary.add_term(decks["himym"], foreign="light", native="světlo").term

    card = card_for(user, decks["himym"], term, Direction.F2N)

    # Own meaning apart; all other dictionary meanings (the browser decides how many fit)
    assert card.own_meanings == [["lehký"]]
    assert card.dictionary_meanings == ["světlý", "dietní", "zapálit", "osvětlit"]


def test_dictionary_meanings_turned_off_in_settings(user, decks, light_entry):
    user.show_other_meanings = False
    user.save()
    vocabulary.add_term(decks["himym"], foreign="light", native="lehký")
    term = vocabulary.add_term(decks["himym"], foreign="light", native="světlo").term

    card = card_for(user, decks["himym"], term, Direction.F2N)

    assert card.own_meanings == [["lehký"]]
    assert card.dictionary_meanings == []


def test_dictionary_meanings_show_only_first_variant(user, decks, lexicon):
    lexicon(
        lexicon_entry(
            "second",
            "noun",
            [
                ("sekunda; vteřina", "A {second}.", "Vteřina."),
                ("moment; okamžik", "Wait a {second}.", "Moment."),
                ("přídavek; nášup", "Can I have {seconds}?", "Přídavek?"),
            ],
        )
    )
    term = vocabulary.add_term(decks["himym"], foreign="second", native="sekunda; vteřina").term

    card = card_for(user, decks["himym"], term, Direction.F2N)

    assert card.dictionary_meanings == ["moment", "přídavek"]


def test_same_translation_is_shown_in_n2f(user, decks):
    vocabulary.add_term(decks["himym"], foreign="hello", native="ahoj")
    hi = vocabulary.add_term(decks["himym"], foreign="hi", native="Ahoj").term

    card = card_for(user, decks["himym"], hi, Direction.N2F)

    assert card.also == ["hello"]
    assert card.front_hint == ""


def test_retry_session_uses_only_its_words(user, decks):
    one = vocabulary.add_term(decks["himym"], foreign="one", native="jedna").term
    vocabulary.add_term(decks["himym"], foreign="two", native="dva")

    session = services.start_session(user, terms=[one], direction=StudyDirection.F2N)

    shown = []
    while (state := services.next_card(session)) is not None:
        shown.append(state.term.main_foreign)
        services.record_answer(session, state, "ok")
    assert shown == ["one"]


def test_translation_of_the_sentence(user, decks):
    term = vocabulary.add_term(
        decks["himym"],
        foreign="palm",
        native="dlaň",
        context_sentence="She can read from her palm.",
        context_sentence_native="Umí číst z {dlaně}.",
    ).term

    card = card_for(user, decks["himym"], term, Direction.N2F)

    # Native → foreign: on the front it tells what goes into the gap; the word in braces marked
    assert card.sentence_native == "Umí číst z <mark>dlaně</mark>."
    assert "___" in card.cloze
