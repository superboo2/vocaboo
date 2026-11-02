"""The first deck of a new user: a small English deck from the dictionary of the app, so a new
account does not start empty and shows at once how decks, folders and tests work.

It is made when the account is confirmed, only for a native language the dictionary has
(the translations come from it). After that it is a usual deck of the user: nothing in it
changes by itself.
"""

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from vocabulary import sentences
from vocabulary import services as vocabulary_services
from vocabulary.models import Language, Term

from .models import ConceptText

FOREIGN = "en"
# Native languages with the first deck
NATIVE = ("cs", "es")

ROOT = gettext_noop("English – first deck")
# (name, name of the parent, concept keys of the words), parents first. Each deck has
# a different number of words, so it is clear how the numbers add up: Animals 7,
# Food 9 (Fruit 5 + Vegetables 4), all 16.
DECKS = (
    (ROOT, None, ""),
    (
        gettext_noop("Animals"),
        ROOT,
        "dog.noun.1 cat.noun.1 horse.noun.1 cow.noun.1 bird.noun.1 fish.noun.2 bear.noun.1",
    ),
    (gettext_noop("Food"), ROOT, ""),
    (
        gettext_noop("Fruit"),
        "Food",
        "apple.noun.1 banana.noun.1 orange.noun.1 strawberry.noun.1 lemon.noun.1",
    ),
    (
        gettext_noop("Vegetables"),
        "Food",
        "carrot.noun.1 potato.noun.1 tomato.noun.1 onion.noun.1",
    ),
)
DESCRIPTION = gettext_noop(
    "An example of a deck with folders. ▶︎ Practice here takes the words of all of them, in "
    "Food only those of Fruit and Vegetables. Add your own words to it, or delete it."
)
# One word for later in Animals, so the card "waiting for a translation" shows up too
PENDING = ("squirrel.noun.1", "Animals")


def create_first_deck(user):
    """Make the first deck of a new user. Returns the top deck, or None when the user has a
    native language without the dictionary, already has decks, or the dictionary is not
    loaded."""
    native = user.native_language
    if native is None or native.code not in NATIVE or user.decks.exists():
        return None
    foreign = Language.objects.filter(code=FOREIGN).first()
    texts = _texts(native.code)
    if foreign is None or not texts:
        return None
    decks = {}
    # The names of the decks are in the user's language, not in the language of the page
    with translation.override(native.code), transaction.atomic():
        for name, parent, keys in DECKS:
            languages = {"foreign_language": foreign, "native_language": native}
            deck = vocabulary_services.create_deck(
                user,
                _(name),
                parent=decks.get(parent),
                **(languages if parent is None else {}),
            )
            decks[name] = deck
            for key in keys.split():
                if key in texts:
                    _add_word(deck, texts[key][FOREIGN], texts[key][native.code])
        root = decks[ROOT]
        root.description = _(DESCRIPTION)
        root.save(update_fields=["description"])
        key, deck_name = PENDING
        if key in texts:
            english = texts[key][FOREIGN]
            vocabulary_services.save_for_later(
                decks[deck_name],
                foreign=english.words.split(";")[0].strip(),
                context_sentence=sentences.plain(english.sentence, []),
            )
    return root


def _add_word(deck, english, own):
    vocabulary_services.add_term(
        deck,
        foreign=english.words,
        native=own.words,
        context_sentence=english.sentence,
        context_sentence_native=own.sentence,
        origin=Term.Origin.DICTIONARY,
    )


def _texts(native_code):
    """concept key -> {language: ConceptText}, only concepts with both texts."""
    keys = [key for *_rest, words in DECKS for key in words.split()] + [PENDING[0]]
    by_key = {}
    for text in ConceptText.objects.filter(
        concept__key__in=keys, language__in=[FOREIGN, native_code]
    ).select_related("concept"):
        by_key.setdefault(text.concept.key, {})[text.language] = text
    return {key: found for key, found in by_key.items() if len(found) == 2}
