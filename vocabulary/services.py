"""Business logic for vocabulary: deck tree rules and words.

Views call these functions and never change decks directly. Errors are raised as
ValidationError with a message that can be shown to the user.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max, Min, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from study.models import Direction, ReviewState

from .models import Deck, DeckTerm, PendingWord, Term, TermVariant

# Maximum number of levels in the deck tree (root = level 1)
MAX_DEPTH = 5


# Reading the tree


def load_tree(owner):
    """Load all decks of the user with one query and link them into a tree.

    Every deck gets `tree_children` (list of decks) and `depth` (root = 1).
    Returns the list of root decks in their order.
    """
    decks = list(
        Deck.objects.filter(owner=owner).select_related("foreign_language", "native_language")
    )
    by_id = {deck.pk: deck for deck in decks}
    roots = []
    for deck in decks:
        deck.tree_children = []
    # Decks come sorted by position, so children are added in the right order
    for deck in decks:
        if deck.parent_id is None:
            roots.append(deck)
        else:
            by_id[deck.parent_id].tree_children.append(deck)
    _set_depth(roots, 1)
    return roots


def _set_depth(decks, depth):
    for deck in decks:
        deck.depth = depth
        _set_depth(deck.tree_children, depth + 1)


def iter_tree(roots, path=()):
    """Go through the tree depth first. Yields (deck, path) where path ends with the deck."""
    for deck in roots:
        deck_path = (*path, deck)
        yield deck, deck_path
        yield from iter_tree(deck.tree_children, deck_path)


def get_ancestors(deck):
    """Return the path from the root to the deck, the deck included."""
    path = [deck]
    current = deck
    while current.parent_id is not None:
        current = current.parent
        path.append(current)
    path.reverse()
    return path


def get_depth(deck):
    return len(get_ancestors(deck))


def get_descendant_ids(deck, include_self=True):
    """Return ids of all decks under the deck (one query per tree level)."""
    ids = [deck.pk] if include_self else []
    level = [deck.pk]
    while level:
        level = list(Deck.objects.filter(parent_id__in=level).values_list("pk", flat=True))
        ids.extend(level)
    return ids


def get_subtree_height(deck):
    """Number of levels from the deck down to its deepest child (deck alone = 1)."""
    height = 1
    level = [deck.pk]
    while True:
        level = list(Deck.objects.filter(parent_id__in=level).values_list("pk", flat=True))
        if not level:
            return height
        height += 1


def get_siblings(deck):
    """Decks with the same parent (the deck included), in their order."""
    return list(Deck.objects.filter(owner_id=deck.owner_id, parent_id=deck.parent_id))


def can_add_child(deck):
    return get_depth(deck) < MAX_DEPTH


def get_move_targets(deck):
    """Decks where this deck can be moved to, as a list of (deck, path).

    Moving to the top level (no parent) is always possible and is not in the list.
    """
    excluded = set(get_descendant_ids(deck))
    height = get_subtree_height(deck)
    targets = []
    for target, path in iter_tree(load_tree(deck.owner)):
        if target.pk in excluded:
            continue
        if not _same_languages(target, deck):
            continue
        if target.depth + height > MAX_DEPTH:
            continue
        targets.append((target, path))
    return targets


# Changing the tree


@transaction.atomic
def create_deck(
    owner,
    name,
    *,
    parent=None,
    foreign_language=None,
    native_language=None,
    description="",
):
    """Create a root deck (languages needed) or a child deck (languages come from parent)."""
    if parent is not None:
        if parent.owner_id != owner.pk:
            raise ValidationError(_("The parent deck belongs to another user."))
        if not can_add_child(parent):
            raise ValidationError(
                _("Decks can have at most %(max)d levels."), params={"max": MAX_DEPTH}
            )
        foreign_language = parent.foreign_language
        native_language = parent.native_language
    elif foreign_language is None or native_language is None:
        raise ValidationError(
            _("Choose the language you want to learn and the language you speak.")
        )

    deck = Deck(
        owner=owner,
        parent=parent,
        name=name.strip(),
        description=description.strip(),
        foreign_language=foreign_language,
        native_language=native_language,
        position=_next_position(owner.pk, parent.pk if parent else None),
    )
    deck.full_clean()
    deck.save()
    return deck


@transaction.atomic
def update_deck(deck, *, name, description=""):
    deck.name = name.strip()
    deck.description = description.strip()
    deck.full_clean()
    deck.save()
    return deck


def _check_move(deck, new_parent):
    """Raise ValidationError when the deck cannot go under new_parent (None = top level)."""
    if new_parent is None:
        return
    if new_parent.owner_id != deck.owner_id:
        raise ValidationError(_("The target deck belongs to another user."))
    if new_parent.pk in get_descendant_ids(deck):
        raise ValidationError(_("A deck cannot be moved into itself or into its own sub-deck."))
    if not _same_languages(new_parent, deck):
        raise ValidationError(
            _("A deck can only be moved under a deck with the same language pair.")
        )
    if get_depth(new_parent) + get_subtree_height(deck) > MAX_DEPTH:
        raise ValidationError(
            _("After the move, the tree would have more than %(max)d levels."),
            params={"max": MAX_DEPTH},
        )


@transaction.atomic
def move_deck(deck, new_parent):
    """Move the deck (with all its children) under another deck, or to the top level."""
    new_parent_id = new_parent.pk if new_parent is not None else None
    if new_parent_id == deck.parent_id:
        return deck
    _check_move(deck, new_parent)

    deck.parent = new_parent
    deck.position = _next_position(deck.owner_id, new_parent_id)
    deck.full_clean()
    deck.save()
    return deck


@transaction.atomic
def place_deck(deck, new_parent, index):
    """Put the deck under new_parent (None = top level) at the given place among its siblings.

    Used by drag and drop in the tree: index 0 is the first place.
    """
    new_parent_id = new_parent.pk if new_parent is not None else None
    if new_parent_id != deck.parent_id:
        _check_move(deck, new_parent)
        deck.parent = new_parent
        # Checks the name: it must not exist in the new folder yet
        deck.full_clean()

    siblings = list(
        Deck.objects.filter(owner_id=deck.owner_id, parent_id=new_parent_id).exclude(pk=deck.pk)
    )
    index = max(0, min(index, len(siblings)))
    siblings.insert(index, deck)
    for position, sibling in enumerate(siblings):
        sibling.position = position
    deck.save()
    Deck.objects.bulk_update(siblings, ["position"])
    return deck


def move_deck_up(deck):
    _shift_deck(deck, -1)


def move_deck_down(deck):
    _shift_deck(deck, 1)


@transaction.atomic
def _shift_deck(deck, step):
    siblings = get_siblings(deck)
    index = next(i for i, sibling in enumerate(siblings) if sibling.pk == deck.pk)
    new_index = index + step
    if not 0 <= new_index < len(siblings):
        return
    siblings[index], siblings[new_index] = siblings[new_index], siblings[index]
    # Renumber all siblings, so positions stay unique and without gaps
    for position, sibling in enumerate(siblings):
        sibling.position = position
    Deck.objects.bulk_update(siblings, ["position"])


def count_terms_deleted_with_deck(deck):
    """How many words would be deleted with the deck: words that are in no other deck."""
    ids = get_descendant_ids(deck)
    inside = Term.objects.filter(deck_terms__deck_id__in=ids).distinct()
    elsewhere = DeckTerm.objects.filter(term__in=inside).exclude(deck_id__in=ids)
    return inside.exclude(pk__in=elsewhere.values("term_id")).count()


@transaction.atomic
def delete_deck(deck):
    """Delete the deck with all its children and the words that stay in no deck.

    Returns (number of deleted decks, number of deleted words).
    """
    ids = get_descendant_ids(deck)
    term_ids = list(
        DeckTerm.objects.filter(deck_id__in=ids).values_list("term_id", flat=True).distinct()
    )
    deck.delete()
    _total, details = Term.objects.filter(pk__in=term_ids, deck_terms__isnull=True).delete()
    return len(ids), _count_deleted(details, Term)


# Words

MAX_VARIANT_LENGTH = 200


def clean_text(text):
    """Tidy user input: one Unicode form (NFC), no spaces at the ends, single spaces inside.

    NFC matters because "č" can come as one character or as "c" + a separate hook,
    which look the same but would not be equal.
    """
    text = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_variants(text):
    """Split "hello; hi" into ["hello", "hi"]. Empty and repeated variants are dropped."""
    variants = []
    seen = set()
    for part in clean_text(text).split(";"):
        part = part.strip()
        key = part.lower()
        if part and key not in seen:
            seen.add(key)
            variants.append(part)
    return variants


def add_term(
    deck,
    *,
    foreign,
    native,
    context_sentence="",
    context_sentence_native="",
    note="",
    origin=Term.Origin.MANUAL,
):
    """Create a new word in the deck. Returns the DeckTerm.

    foreign and native are texts like "hello; hi". Creates the word, its variants,
    the link to the deck and the review states for both directions in one transaction.
    The same foreign word with another translation is another meaning, so it is allowed:
    palm → dlaň and palm → palma.
    """
    foreign_variants = _parse_side(foreign, "foreign")
    native_variants = _parse_side(native, "native")
    _check_no_duplicate(
        deck.owner_id,
        deck.foreign_language_id,
        deck.native_language_id,
        foreign_variants[0],
        native_variants[0],
    )

    with transaction.atomic():
        term = Term(
            owner_id=deck.owner_id,
            foreign_language_id=deck.foreign_language_id,
            native_language_id=deck.native_language_id,
            main_foreign=foreign_variants[0],
            main_native=native_variants[0],
            note=clean_text(note),
            origin=origin,
        )
        term.save()
        _save_variants(term, foreign_variants, native_variants)
        deck_term = DeckTerm(
            deck=deck,
            term=term,
            context_sentence=clean_text(context_sentence),
            context_sentence_native=clean_text(context_sentence_native),
        )
        deck_term.full_clean(exclude=["deck", "term"])
        deck_term.save()
        ReviewState.objects.bulk_create(
            ReviewState(term=term, direction=direction) for direction in Direction.values
        )
    return deck_term


@transaction.atomic
def update_term(term, *, foreign, native, note=""):
    """Change the texts of a word. The variants are replaced by the new ones."""
    foreign_variants = _parse_side(foreign, "foreign")
    native_variants = _parse_side(native, "native")
    _check_no_duplicate(
        term.owner_id,
        term.foreign_language_id,
        term.native_language_id,
        foreign_variants[0],
        native_variants[0],
        exclude_pk=term.pk,
    )

    term.main_foreign = foreign_variants[0]
    term.main_native = native_variants[0]
    term.note = clean_text(note)
    term.save()
    term.variants.all().delete()
    _save_variants(term, foreign_variants, native_variants)
    return term


@transaction.atomic
def update_deck_term(deck_term, *, context_sentence="", context_sentence_native=""):
    """Change the sentence of a word in one deck and its translation."""
    deck_term.context_sentence = clean_text(context_sentence)
    deck_term.context_sentence_native = clean_text(context_sentence_native)
    deck_term.full_clean(exclude=["deck", "term"])
    deck_term.save()
    return deck_term


def term_is_only_in(deck_term):
    """True when the word is in no other deck, so removing it deletes the word."""
    return not DeckTerm.objects.filter(term_id=deck_term.term_id).exclude(pk=deck_term.pk).exists()


@transaction.atomic
def remove_term_from_deck(deck_term):
    """Remove the word from the deck. A word in no other deck is deleted.

    Returns True when the word was deleted.
    """
    term = deck_term.term
    deck_term.delete()
    if not term.deck_terms.exists():
        term.delete()
        return True
    return False


# Duplicates


@dataclass
class TermMatch:
    """An existing word that looks like the word being typed."""

    term: Term
    deck_names: list
    # The DeckTerm when the word is already in the checked deck
    in_deck: DeckTerm | None
    # Typed variants the existing word does not have yet
    new_foreign: list
    new_native: list


@dataclass
class DuplicateCheck:
    """What the user should know before saving a new word. See spec 5.1."""

    # Same main foreign text and same main translation: the new word cannot be saved
    exact: TermMatch | None = None
    # Same main foreign text with another translation: other meanings of the word.
    # Saving is allowed (another meaning), or the typed word can be added to one of them.
    meanings: list = field(default_factory=list)
    # Other words that share a foreign variant
    foreign: list = field(default_factory=list)
    # Words that share only a translation
    native: list = field(default_factory=list)
    # Same letters when accents are ignored, e.g. "cau" and "čau"
    similar: list = field(default_factory=list)

    @property
    def blocks(self):
        return self.exact is not None

    def __bool__(self):
        return bool(self.exact or self.meanings or self.foreign or self.native or self.similar)


def find_duplicates(deck, *, foreign="", native=""):
    """Look for words of the user that look like the typed one.

    Compares every typed variant with every variant of existing words: first with letter
    case ignored, then also with accents ignored (PostgreSQL unaccent).
    """
    foreign_variants = parse_variants(foreign)
    native_variants = parse_variants(native)
    check = DuplicateCheck()
    if not foreign_variants and not native_variants:
        return check

    conditions = [
        Q(variants__side=side, variants__text__unaccent__iexact=text)
        for side, texts in (
            (TermVariant.Side.FOREIGN, foreign_variants),
            (TermVariant.Side.NATIVE, native_variants),
        )
        for text in texts
    ]
    candidates = (
        Term.objects.filter(
            reduce(or_, conditions),
            owner_id=deck.owner_id,
            foreign_language_id=deck.foreign_language_id,
            native_language_id=deck.native_language_id,
        )
        .distinct()
        .prefetch_related("variants", "deck_terms__deck")
        .order_by("main_foreign", "main_native")
    )

    typed_foreign = {text.lower() for text in foreign_variants}
    typed_native = {text.lower() for text in native_variants}
    main = foreign_variants[0].lower() if foreign_variants else None
    main_native = native_variants[0].lower() if native_variants else None

    for term in candidates:
        has_foreign = {text.lower() for text in term.foreign_variants}
        has_native = {text.lower() for text in term.native_variants}
        deck_terms = list(term.deck_terms.all())
        match = TermMatch(
            term=term,
            deck_names=[item.deck.name for item in deck_terms],
            in_deck=next((item for item in deck_terms if item.deck_id == deck.pk), None),
            new_foreign=[v for v in foreign_variants if v.lower() not in has_foreign],
            new_native=[v for v in native_variants if v.lower() not in has_native],
        )
        same_main = main is not None and term.main_foreign.lower() == main
        if same_main and main_native is not None and term.main_native.lower() == main_native:
            check.exact = match
        elif same_main:
            check.meanings.append(match)
        elif typed_foreign & has_foreign:
            check.foreign.append(match)
        elif typed_native & has_native:
            check.native.append(match)
        else:
            check.similar.append(match)
    return check


@transaction.atomic
def link_term(
    deck, term, *, foreign="", native="", context_sentence="", context_sentence_native=""
):
    """Put an existing word into the deck and add the typed variants it does not have yet.

    Used by "Přidat i sem" and "Přidat jako variantu". Returns (DeckTerm, added variants).
    """
    if (term.owner_id, term.foreign_language_id, term.native_language_id) != (
        deck.owner_id,
        deck.foreign_language_id,
        deck.native_language_id,
    ):
        raise ValidationError(_("The word does not belong to this deck."))

    added = []
    for side, text in ((TermVariant.Side.FOREIGN, foreign), (TermVariant.Side.NATIVE, native)):
        variants = parse_variants(text)
        if any(len(variant) > MAX_VARIANT_LENGTH for variant in variants):
            raise ValidationError(
                _("A variant can have at most %(max)d characters.") % {"max": MAX_VARIANT_LENGTH}
            )
        current = list(term.variants.filter(side=side))
        known = {variant.text.lower() for variant in current}
        position = max((variant.position for variant in current), default=-1) + 1
        for variant in variants:
            if variant.lower() in known:
                continue
            TermVariant.objects.create(term=term, side=side, text=variant, position=position)
            known.add(variant.lower())
            added.append(variant)
            position += 1

    deck_term = DeckTerm.objects.filter(deck=deck, term=term).first()
    if deck_term is None:
        deck_term = DeckTerm(
            deck=deck,
            term=term,
            context_sentence=clean_text(context_sentence),
            context_sentence_native=clean_text(context_sentence_native),
        )
        deck_term.full_clean(exclude=["deck", "term"])
        deck_term.save()
    return deck_term, added


def get_term_move_targets(deck):
    """Decks where words of this deck can be moved or copied to, as a list of (deck, path)."""
    return [
        (target, path)
        for target, path in iter_tree(load_tree(deck.owner))
        if target.pk != deck.pk and _same_languages(target, deck)
    ]


@transaction.atomic
def move_deck_terms(deck_terms, target, *, copy=False):
    """Move words into another deck, or with copy=True put them there too.

    The word itself, its variants and its review progress stay the same, only the deck
    changes. When the word is already in the target deck, nothing is doubled: the target
    keeps its own entry and only gets the sentence when it has none.
    Returns (number of words done, number of words that were already in the target).
    """
    done = already = 0
    for deck_term in deck_terms:
        if deck_term.deck.owner_id != target.owner_id or not _same_languages(
            deck_term.deck, target
        ):
            raise ValidationError(_("Words can only be moved to a deck with the same languages."))
        if deck_term.deck_id == target.pk:
            continue
        existing = DeckTerm.objects.filter(deck=target, term_id=deck_term.term_id).first()
        if existing is not None:
            if not existing.context_sentence and deck_term.context_sentence:
                existing.context_sentence = deck_term.context_sentence
                existing.context_sentence_native = deck_term.context_sentence_native
                existing.save(update_fields=["context_sentence", "context_sentence_native"])
            if not copy:
                deck_term.delete()
            already += 1
        elif copy:
            DeckTerm.objects.create(
                deck=target,
                term_id=deck_term.term_id,
                context_sentence=deck_term.context_sentence,
                context_sentence_native=deck_term.context_sentence_native,
            )
        else:
            deck_term.deck = target
            deck_term.save(update_fields=["deck"])
        done += 1
    return done, already


# Sort options for the word list in a deck
TERM_SORTS = {
    "added": gettext_lazy("by date added"),
    "alpha": gettext_lazy("alphabetically"),
    "due": gettext_lazy("by next review"),
}


def list_deck_terms(deck, sort="added"):
    """Words in one deck with their variants, ready to show."""
    queryset = DeckTerm.objects.filter(deck=deck).select_related("term")
    queryset = queryset.prefetch_related("term__variants")
    if sort == "alpha":
        queryset = queryset.order_by(Lower("term__main_foreign"), "pk")
    elif sort == "due":
        # The direction that comes back first decides; new words go last
        queryset = queryset.annotate(next_due=Min("term__review_states__due_at")).order_by(
            F("next_due").asc(nulls_last=True), "-added_at"
        )
    else:
        queryset = queryset.order_by("-added_at", "-pk")
    return queryset


def save_for_later(deck, *, foreign, context_sentence="", note=""):
    """Save a foreign word without a translation ("Na později"). Returns the PendingWord."""
    foreign = foreign.strip()
    if not foreign:
        raise ValidationError({"foreign": _("Enter the word.")})
    if len(foreign) > MAX_VARIANT_LENGTH:
        raise ValidationError(
            {
                "foreign": _("A variant can have at most %(max)d characters.")
                % {"max": MAX_VARIANT_LENGTH}
            }
        )
    return PendingWord.objects.create(
        owner=deck.owner,
        deck=deck,
        foreign=foreign,
        context_sentence=context_sentence.strip(),
        note=note.strip(),
    )


def pending_words(user, deck=None):
    """The user's words for later, the newest first; only of one deck when it is given."""
    words = PendingWord.objects.filter(owner=user).select_related(
        "deck__foreign_language", "deck__native_language"
    )
    return words.filter(deck=deck) if deck is not None else words


def _parse_side(text, field):
    variants = parse_variants(text)
    if not variants:
        raise ValidationError({field: _("Enter at least one variant.")})
    for variant in variants:
        if len(variant) > MAX_VARIANT_LENGTH:
            raise ValidationError(
                {
                    field: _("A variant can have at most %(max)d characters.")
                    % {"max": MAX_VARIANT_LENGTH}
                }
            )
    return variants


def _check_no_duplicate(
    owner_id, foreign_language_id, native_language_id, main_foreign, main_native, exclude_pk=None
):
    """Stop a second word with the same main text and the same translation (any letter case)."""
    existing = Term.objects.filter(
        owner_id=owner_id,
        foreign_language_id=foreign_language_id,
        native_language_id=native_language_id,
        main_foreign__iexact=main_foreign,
        main_native__iexact=main_native,
    )
    if exclude_pk is not None:
        existing = existing.exclude(pk=exclude_pk)
    term = existing.first()
    if term is None:
        return
    deck_names = ", ".join(term.deck_terms.values_list("deck__name", flat=True))
    raise ValidationError(
        {
            "foreign": _("You already have the word “%(word)s → %(native)s” (%(decks)s).")
            % {"word": term.main_foreign, "native": term.main_native, "decks": deck_names}
        }
    )


def _save_variants(term, foreign_variants, native_variants):
    TermVariant.objects.bulk_create(
        [
            TermVariant(term=term, side=side, text=text, position=position)
            for side, variants in (
                (TermVariant.Side.FOREIGN, foreign_variants),
                (TermVariant.Side.NATIVE, native_variants),
            )
            for position, text in enumerate(variants)
        ]
    )


# Helpers


def _count_deleted(details, model):
    return details.get(model._meta.label, 0)


def _next_position(owner_id, parent_id):
    last = Deck.objects.filter(owner_id=owner_id, parent_id=parent_id).aggregate(
        last=Max("position")
    )["last"]
    return 0 if last is None else last + 1


def _same_languages(a, b):
    return (a.foreign_language_id, a.native_language_id) == (
        b.foreign_language_id,
        b.native_language_id,
    )


# Search in the user's words (the page "Hledat" and the field on the dashboard)
SEARCH_MIN_LENGTH = 2
SEARCH_LIMIT = 50
# How many decks of a path are shown (the whole path is in the title)
PATH_LEVELS = 3


def _fold(text):
    """Lower case without accents, one letter for one letter: "Četka" → "cetka".

    The text keeps its length, so a place found in the folded text is the same place in
    the original one (for marking the match)."""
    return "".join(unicodedata.normalize("NFD", char)[0] for char in text.lower())


def deck_names(owner):
    """Names and parents of all decks of the user, for deck_path."""
    return {
        pk: (name, parent_id)
        for pk, name, parent_id in Deck.objects.filter(owner=owner).values_list(
            "pk", "name", "parent_id"
        )
    }


def deck_path(deck_id, names):
    """The path of the deck from the root, e.g. "CzechEnglish › series › S01 › E02": in short
    only the last PATH_LEVELS decks ("… › series › S01 › E02"), the whole path for the title."""
    path = []
    while deck_id is not None:
        name, deck_id = names[deck_id]
        path.append(name)
    path.reverse()
    short = path[-PATH_LEVELS:]
    if len(path) > PATH_LEVELS:
        short = ["…", *short]
    return {"short": " › ".join(short), "full": " › ".join(path)}


@dataclass
class SearchHit:
    term: Term
    # The word in its first deck (for the links) and all its decks (paths)
    deck_term: DeckTerm
    paths: list
    # Texts with the match marked (lists of (text, is_match) parts)
    foreign: list
    native: list
    # The sentence or note where the query was found, when it was not in the word
    found_in: list = field(default_factory=list)


def search_terms(owner, query, limit=SEARCH_LIMIT):
    """Words of the user with the query in a variant, a sentence or the note.

    Without accents and case ("cetka" finds "Četka"). The words with the query in the word or
    the translation come first, then the ones with it in a sentence or the note; each group
    is sorted by the word. The user has at most a few thousand words, so they are searched
    in Python.
    """
    needle = _fold(query.strip())
    if len(needle) < SEARCH_MIN_LENGTH:
        return []
    names = deck_names(owner)
    terms = (
        Term.objects.filter(owner=owner, deck_terms__isnull=False)
        .distinct()
        .prefetch_related("variants", "deck_terms")
        .order_by(Lower("main_foreign"), "pk")
    )
    in_word = []
    in_other = []
    for term in terms:
        foreign = "; ".join(term.foreign_variants)
        native = "; ".join(term.native_variants)
        deck_terms = sorted(term.deck_terms.all(), key=lambda item: (item.added_at, item.pk))
        hit = SearchHit(
            term=term,
            deck_term=deck_terms[0],
            paths=[deck_path(item.deck_id, names) for item in deck_terms],
            foreign=_mark(foreign, needle),
            native=_mark(native, needle),
        )
        if needle in _fold(foreign) or needle in _fold(native):
            in_word.append(hit)
            continue
        others = [
            text
            for item in deck_terms
            for text in (item.context_sentence, item.context_sentence_native)
            if text
        ] + [term.note]
        found = next((text for text in others if text and needle in _fold(text)), None)
        if found:
            # The braces that mark the word in a sentence are not shown
            hit.found_in = _mark(found.replace("{", "").replace("}", ""), needle)
            in_other.append(hit)
    return (in_word + in_other)[:limit]


def _mark(text, needle):
    """The text cut into parts, the matches of the needle marked: [("trin", True), ...]."""
    folded = _fold(text)
    parts = []
    start = 0
    while needle and (found := folded.find(needle, start)) != -1:
        if found > start:
            parts.append((text[start:found], False))
        parts.append((text[found : found + len(needle)], True))
        start = found + len(needle)
    if start < len(text):
        parts.append((text[start:], False))
    return parts
