"""Words of a topic from the dictionary of the app, offered for a deck: the user ticks the ones
to learn, they become the user's own words (copies). Nothing is added in bulk: one page of at
most PAGE words, no "select all".
"""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from vocabulary import services as vocabulary_services
from vocabulary.models import DeckTerm, Term

from .models import LexiconEntry, LexiconSense, LexiconTag

# At most this many words on a page, and in one adding
PAGE = 20
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
DEFAULT_LEVELS = ("A1", "A2", "B1")
# Groups of parts of speech for the filter; "other" is everything else (adverbs, phrases …)
POS_GROUPS = {
    "noun": (_("nouns"), ["noun"]),
    "verb": (_("verbs"), ["verb"]),
    "adjective": (_("adjectives"), ["adjective"]),
    "other": (_("other"), None),
}
# Tags of the style of speech and of grammar words are no topics; vulgar meanings are never offered
NOT_TOPICS = {"styl", "hovorove", "formalni", "vulgarni", "gramatika"}
NEVER_OFFERED = "vulgarni"

# Names of the topics in the language of the page (the tags file has them in Czech only)
TOPIC_NAMES = {
    "clovek": _("People"),
    "telo": _("Body"),
    "zdravi": _("Health and illness"),
    "rodina": _("Family and relationships"),
    "city": _("Feelings and moods"),
    "povaha": _("Character"),
    "vzhled": _("Appearance"),
    "obleceni": _("Clothes"),
    "jidlo": _("Food and drink"),
    "ovoce": _("Fruit"),
    "zelenina": _("Vegetables"),
    "napoje": _("Drinks"),
    "vareni": _("Cooking and kitchen"),
    "domov": _("Home"),
    "nabytek": _("Furniture and things at home"),
    "domacnost": _("Housework"),
    "priroda": _("Nature"),
    "zvire": _("Animals"),
    "rostlina": _("Plants"),
    "pocasi": _("Weather"),
    "krajina": _("Landscape"),
    "mesto": _("Town and places"),
    "budovy": _("Buildings"),
    "doprava": _("Transport"),
    "nakupovani": _("Shopping"),
    "cestovani": _("Travel"),
    "prace": _("Work and school"),
    "skola": _("School and learning"),
    "zamestnani": _("Jobs"),
    "penize": _("Money"),
    "kancelar": _("Office"),
    "volny_cas": _("Free time"),
    "sport": _("Sport"),
    "hudba": _("Music"),
    "film": _("Films and series"),
    "hry": _("Games"),
    "umeni": _("Art and culture"),
    "komunikace": _("Communication"),
    "pozdravy": _("Greetings and politeness"),
    "konverzace": _("Everyday conversation"),
    "technika": _("Phone, computer, internet"),
    "media": _("News and media"),
    "spolecnost": _("Society"),
    "pravo": _("Law and crime"),
    "politika": _("Politics"),
    "valka": _("War and army"),
    "nabozenstvi": _("Religion"),
    "cas": _("Time"),
    "kalendar": _("Days, months, seasons"),
    "mnozstvi": _("Numbers and amounts"),
    "barva": _("Colours"),
    "prostor": _("Place, direction, position"),
    "pohyb": _("Movement"),
    "smysly": _("Senses"),
    "mysleni": _("Thinking and knowing"),
}


@dataclass
class Topic:
    tag: LexiconTag
    name: str
    children: list = field(default_factory=list)


@dataclass
class TopicCounts:
    """How many words the topic has for the chosen levels, and where the user has them."""

    total: int = 0
    # Already in this deck (never offered) and in other decks (hidden unless asked for)
    here: int = 0
    elsewhere: int = 0


@dataclass
class TopicWord:
    sense: LexiconSense
    word: str
    translation: str
    level: str
    # Names of the user's other decks that already have this word with this meaning
    other_decks: list


def has_dictionary(deck):
    """The dictionary of the app has words for the language pair of the deck."""
    return LexiconEntry.objects.filter(
        foreign_code=deck.foreign_language.code, native_code=deck.native_language.code
    ).exists()


def topic_name(tag):
    return str(TOPIC_NAMES.get(tag.slug, tag.name))


def topics():
    """The topics for the choice: groups (e.g. Nature) with their topics (Animals …)."""
    tags = [tag for tag in LexiconTag.objects.order_by("pk") if tag.slug not in NOT_TOPICS]
    groups = {tag.pk: Topic(tag, topic_name(tag)) for tag in tags if tag.parent_id is None}
    for tag in tags:
        if tag.parent_id in groups:
            groups[tag.parent_id].children.append(Topic(tag, topic_name(tag)))
    return list(groups.values())


def find_topic(slug):
    if slug in NOT_TOPICS:
        return None
    return LexiconTag.objects.filter(slug=slug).first()


def pos_filter(groups):
    """Q of the parts of speech of the chosen groups (all groups: no filter)."""
    if not groups or set(groups) >= set(POS_GROUPS):
        return Q()
    named = [pos for _name, kinds in POS_GROUPS.values() if kinds for pos in kinds]
    query = Q(
        entry__part_of_speech__in=[
            pos for key in groups if POS_GROUPS[key][1] for pos in POS_GROUPS[key][1]
        ]
    )
    if "other" in groups:
        query |= ~Q(entry__part_of_speech__in=named)
    return query


def topic_words(deck, tag, levels, page=1, show_owned=False, pos_groups=None):
    """One page of words of the topic for the deck, the most common first.

    Words that are already in this deck with the same meaning are left out. The ones in another
    deck of the user are left out too (so a second deck of the same topic starts with new
    words), unless show_owned: then they stay, greyed with the names of those decks.
    Returns (list of TopicWord, there is a next page, TopicCounts).
    """
    tag_ids = [tag.pk, *tag.children.values_list("pk", flat=True)]
    senses = (
        LexiconSense.objects.filter(
            tags__in=tag_ids,
            entry__level__in=levels,
            entry__foreign_code=deck.foreign_language.code,
            entry__native_code=deck.native_language.code,
        )
        .filter(pos_filter(pos_groups))
        .exclude(tags__slug=NEVER_OFFERED)
        .select_related("entry")
        .distinct()
        .order_by("entry__band", "entry__word", "position")
    )
    owned = _owned_words(deck)
    words = []
    counts = TopicCounts()
    for sense in senses:
        counts.total += 1
        decks = owned.get(_key(sense.entry.word, sense.translation), {})
        if deck.pk in decks:
            counts.here += 1
            continue
        if decks:
            counts.elsewhere += 1
            if not show_owned:
                continue
        words.append(
            TopicWord(
                sense=sense,
                word=sense.entry.word,
                translation=sense.translation,
                level=sense.entry.level,
                other_decks=sorted(decks.values()),
            )
        )
    start = (page - 1) * PAGE
    return words[start : start + PAGE], len(words) > start + PAGE, counts


def add_topic_words(deck, sense_ids):
    """Add the chosen meanings to the deck as the user's own words (with the sentence).

    At most PAGE at once; words the user already has are skipped. Returns the added DeckTerms.
    """
    senses = LexiconSense.objects.filter(
        pk__in=list(sense_ids)[:PAGE],
        entry__foreign_code=deck.foreign_language.code,
        entry__native_code=deck.native_language.code,
    ).select_related("entry")
    added = []
    for sense in senses.exclude(tags__slug=NEVER_OFFERED).order_by("entry__band", "position"):
        try:
            added.append(
                vocabulary_services.add_term(
                    deck,
                    foreign=sense.entry.word,
                    native=sense.translation,
                    context_sentence=sense.sentence,
                    context_sentence_native=sense.sentence_native,
                    origin=Term.Origin.DICTIONARY,
                )
            )
        except ValidationError:
            # The user has this word already (in this or another deck)
            continue
    return added


def _key(foreign, native):
    # The word and the first variant of its translation: the same as the main texts of a word
    return foreign.strip().lower(), native.split(";")[0].strip().lower()


def _owned_words(deck):
    """(foreign, native) of the user's words in this language pair -> {deck id: deck name}."""
    owned = {}
    rows = DeckTerm.objects.filter(
        deck__owner_id=deck.owner_id,
        term__foreign_language_id=deck.foreign_language_id,
        term__native_language_id=deck.native_language_id,
    ).values_list("term__main_foreign", "term__main_native", "deck_id", "deck__name")
    for foreign, native, deck_id, name in rows:
        owned.setdefault(_key(foreign, native), {})[deck_id] = name
    return owned
