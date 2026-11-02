"""The first deck of a new user, made from the dictionary of the app."""

import pytest
from django.urls import reverse

from dictionary import starter
from tests.conftest import lexicon_entry
from vocabulary import services
from vocabulary.models import Deck, DeckTerm, PendingWord, Term

# A part of the words of the first deck (the rest is not in this small dictionary)
WORDS = (
    lexicon_entry("dog", "noun", [("pes", "Our {dog} loves the park.", "Náš pes miluje park.")]),
    lexicon_entry("cat", "noun", [("kočka", "The {cat} sleeps.", "Kočka spí.")]),
    lexicon_entry("apple", "noun", [("jablko", "An {apple} a day.", "Jablko denně.")]),
    lexicon_entry("carrot", "noun", [("mrkev", "Peel the {carrots}.", "Oloupej mrkev.")]),
    lexicon_entry("squirrel", "noun", [("veverka", "Look, a {squirrel}!", "Hele, veverka!")]),
)


@pytest.fixture
def new_user(user, cs):
    user.native_language = cs
    user.save()
    return user


def test_first_deck_is_a_tree_in_the_users_language(lexicon, new_user, en, cs):
    lexicon(*WORDS)

    root = starter.create_first_deck(new_user)

    assert (root.name, root.foreign_language, root.native_language) == (
        "Angličtina – první slovníček",
        en,
        cs,
    )
    assert "Ukázka slovníku se složkami" in root.description
    tree = {deck.name: deck.parent.name if deck.parent else None for deck in Deck.objects.all()}
    assert tree == {
        "Angličtina – první slovníček": None,
        "Zvířata": "Angličtina – první slovníček",
        "Jídlo": "Angličtina – první slovníček",
        "Ovoce": "Jídlo",
        "Zelenina": "Jídlo",
    }
    words = {
        (item.deck.name, item.term.main_foreign, item.term.main_native)
        for item in DeckTerm.objects.select_related("deck", "term")
    }
    assert words == {
        ("Zvířata", "dog", "pes"),
        ("Zvířata", "cat", "kočka"),
        ("Ovoce", "apple", "jablko"),
        ("Zelenina", "carrot", "mrkev"),
    }
    dog = DeckTerm.objects.get(term__main_foreign="dog")
    assert dog.context_sentence == "Our {dog} loves the park."
    assert dog.context_sentence_native == "Náš pes miluje park."
    assert dog.term.origin == Term.Origin.DICTIONARY
    # One word for later, without braces in the sentence
    pending = PendingWord.objects.get()
    assert (pending.deck.name, pending.foreign, pending.context_sentence) == (
        "Zvířata",
        "squirrel",
        "Look, a squirrel!",
    )


def test_numbers_of_words_differ_in_each_deck():
    counts = [len(keys.split()) for _name, _parent, keys in starter.DECKS if keys]

    assert counts == [7, 5, 4]


def test_no_first_deck_without_the_dictionary_or_for_other_languages(
    lexicon, new_user, other_user, en, cs
):
    # The dictionary is not loaded
    assert starter.create_first_deck(new_user) is None

    lexicon(*WORDS)
    # English as the native language: nothing to translate into
    other_user.native_language = en
    other_user.save()
    assert starter.create_first_deck(other_user) is None
    # The user already has a deck
    services.create_deck(new_user, "Moje", foreign_language=en, native_language=cs)
    assert starter.create_first_deck(new_user) is None
    assert Deck.objects.count() == 1


def test_confirmed_account_gets_the_first_deck(lexicon, client, mailoutbox, cs):
    lexicon(*WORDS)
    client.post(
        reverse("register"),
        {
            "email": "new@example.com",
            "password1": "secret-pass-123",
            "password2": "secret-pass-123",
            "native_language": cs.pk,
        },
    )
    # Not before the email is confirmed
    assert not Deck.objects.exists()

    code = next(word for word in mailoutbox[0].subject.split() if word.isdigit())
    client.post(reverse("verify_email"), {"code": code})

    assert Deck.objects.filter(owner__email="new@example.com").count() == 5
    html = client.get(reverse("dashboard")).content.decode()
    assert "Angličtina – první slovníček" in html
    assert "odložené čeká na překlad" in html
