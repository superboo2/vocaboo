"""Words from a topic: the user ticks words of the dictionary of the app and adds them."""

import pytest
from django.urls import reverse

from dictionary import topics
from tests.conftest import lexicon_entry
from vocabulary import services
from vocabulary.models import Term

TAGS = (
    {"slug": "priroda", "name": "příroda", "parent": None},
    {"slug": "zvire", "name": "zvířata", "parent": "priroda"},
    {"slug": "rostlina", "name": "rostliny", "parent": "priroda"},
    {"slug": "vulgarni", "name": "vulgární", "parent": None},
)
DOG = lexicon_entry("dog", "noun", [("pes", "The {dog} barks.", "Pes štěká.", "", ["zvire"])])
CAT = lexicon_entry(
    "cat", "noun", [("kočka; kocour", "The {cat} sleeps.", "{Kočka} spí.", "", ["zvire"])], band=2
)
BEAR = lexicon_entry(
    "bear",
    "noun",
    [("medvěd", "A {bear} in the forest.", "Medvěd v lese.", "", ["zvire"])],
    band=3,
)
TREE = lexicon_entry(
    "tree", "noun", [("strom", "A tall {tree}.", "Vysoký strom.", "", ["rostlina"])]
)
RUDE = lexicon_entry(
    "bitch", "noun", [("fena", "The {bitch} had puppies.", "Fena.", "", ["zvire", "vulgarni"])]
)


@pytest.fixture
def deck(lexicon, user, en, cs):
    lexicon(DOG, CAT, BEAR, TREE, RUDE, tags=TAGS)
    return services.create_deck(user, "Zvířata", foreign_language=en, native_language=cs)


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


def url(deck, **query):
    from urllib.parse import urlencode

    return reverse("vocabulary:topic_words", args=[deck.pk]) + "?" + urlencode(query, doseq=True)


def test_words_of_a_topic_most_common_first(deck):
    words, has_next, _counts = topics.topic_words(
        deck, topics.find_topic("zvire"), ["A1", "A2", "B1"]
    )

    assert [item.word for item in words] == ["dog", "cat", "bear"]
    assert has_next is False
    # A group has the words of all its topics; vulgar meanings are never offered
    group = topics.topic_words(deck, topics.find_topic("priroda"), ["A1"])[0]
    assert sorted(item.word for item in group) == ["bear", "cat", "dog", "tree"]


def test_words_already_in_the_deck_or_elsewhere(deck, user, en, cs):
    services.add_term(deck, foreign="dog", native="pes")
    other = services.create_deck(user, "Seriály", foreign_language=en, native_language=cs)
    services.add_term(other, foreign="cat", native="kočka")

    words, _next, counts = topics.topic_words(deck, topics.find_topic("zvire"), ["A1"])
    shown = topics.topic_words(deck, topics.find_topic("zvire"), ["A1"], show_owned=True)[0]

    # dog is in this deck: never offered; cat is elsewhere: hidden, or greyed when asked for
    assert [item.word for item in words] == ["bear"]
    assert (counts.total, counts.here, counts.elsewhere) == (3, 1, 1)
    assert [(item.word, item.other_decks) for item in shown] == [("cat", ["Seriály"]), ("bear", [])]


def test_page_shows_topics_and_words(logged_client, deck):
    html = logged_client.get(url(deck, topic="zvire")).content.decode()

    assert "Slovíčka z tématu" in html
    assert 'value="zvire" selected' in html
    assert "dog" in html and "bear" in html
    assert "bitch" not in html
    # Style tags are no topics
    assert 'value="vulgarni"' not in html


def test_ticked_words_are_added_with_their_sentence(logged_client, deck):
    words = topics.topic_words(deck, topics.find_topic("zvire"), ["A1"])[0]
    dog, cat = words[0].sense, words[1].sense

    response = logged_client.post(url(deck, topic="zvire"), {"sense": [dog.pk, cat.pk]})

    assert response.status_code == 302
    added = {item.term.main_foreign: item for item in deck.deck_terms.select_related("term")}
    assert sorted(added) == ["cat", "dog"]
    assert added["cat"].term.main_native == "kočka"
    assert added["cat"].context_sentence == "The {cat} sleeps."
    assert added["dog"].term.origin == Term.Origin.DICTIONARY
    # Back on the same page, without the added words
    page = logged_client.get(response.url).content.decode()
    assert "Přidána 2 slovíčka do „Zvířata“." in page


def test_at_most_one_page_at_once(deck):
    assert topics.PAGE == 20
    added = topics.add_topic_words(deck, [sense for sense in range(1, 1000)])

    assert len(added) <= topics.PAGE


def test_deck_page_links_only_with_a_dictionary(logged_client, deck, user, es, cs):
    spanish = services.create_deck(user, "Español", foreign_language=es, native_language=cs)

    english_page = logged_client.get(reverse("vocabulary:deck_detail", args=[deck.pk]))
    spanish_page = logged_client.get(reverse("vocabulary:deck_detail", args=[spanish.pk]))

    assert reverse("vocabulary:topic_words", args=[deck.pk]) in english_page.content.decode()
    spanish_link = reverse("vocabulary:topic_words", args=[spanish.pk])
    assert spanish_link not in spanish_page.content.decode()
    assert logged_client.get(url(spanish, topic="zvire")).status_code == 404


def test_parts_of_speech_filter(lexicon, deck):
    walk = lexicon_entry(
        "walk", "verb", [("vyvenčit", "{Walk} the dog.", "Vyvenči psa.", "", ["zvire"])]
    )
    lexicon(DOG, CAT, BEAR, TREE, RUDE, walk, tags=TAGS)
    animals = topics.find_topic("zvire")

    nouns = topics.topic_words(deck, animals, ["A1"], pos_groups=["noun"])[0]
    verbs = topics.topic_words(deck, animals, ["A1"], pos_groups=["verb"])[0]
    others = topics.topic_words(deck, animals, ["A1"], pos_groups=["other"])[0]
    every = topics.topic_words(deck, animals, ["A1"], pos_groups=list(topics.POS_GROUPS))[0]

    assert [item.word for item in nouns] == ["dog", "cat", "bear"]
    assert [item.word for item in verbs] == ["walk"]
    assert others == []
    assert len(every) == 4


def test_topic_words_for_a_czech_english_deck(deck, user, en, cs):
    czech = services.create_deck(user, "Zvířata CS", foreign_language=cs, native_language=en)

    words = topics.topic_words(czech, topics.find_topic("zvire"), ["A1"])[0]

    # The Czech words with their English translation, in the order of the English words
    assert [(item.word, item.translation) for item in words] == [
        ("pes", "dog"),
        ("kočka; kocour", "cat"),
        ("medvěd", "bear"),
    ]
    assert topics.has_dictionary(czech)
    added = topics.add_topic_words(czech, [words[1].sense.pk])
    assert (added[0].term.main_foreign, added[0].term.main_native) == ("kočka", "cat")
    assert added[0].context_sentence == "{Kočka} spí."
