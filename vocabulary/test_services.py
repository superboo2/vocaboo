import pytest
from django.core.exceptions import ValidationError

from . import services
from .models import Deck


@pytest.fixture
def make_deck(user, en, cs):
    """Create a deck quickly: make_deck("HIMYM", parent=series)."""

    def make(name, parent=None, owner=None, foreign=None, native=None):
        return services.create_deck(
            owner or user,
            name,
            parent=parent,
            foreign_language=foreign or en,
            native_language=native or cs,
        )

    return make


@pytest.fixture
def chain(make_deck):
    """Five levels: English › Series › HIMYM › S01 › E01."""
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    himym = make_deck("HIMYM", parent=series)
    season = make_deck("S01", parent=himym)
    episode = make_deck("E01", parent=season)
    return [english, series, himym, season, episode]


def names(decks):
    return [deck.name for deck in decks]


# Creating


def test_create_root_deck(user, en, cs):
    deck = services.create_deck(
        user, "  Angličtina  ", foreign_language=en, native_language=cs, description=" x "
    )

    assert deck.name == "Angličtina"
    assert deck.description == "x"
    assert deck.parent is None
    assert deck.language_pair == "EN → CS"


def test_root_deck_needs_languages(user, en):
    with pytest.raises(ValidationError):
        services.create_deck(user, "Angličtina", foreign_language=en)


def test_root_deck_languages_must_differ(user, cs):
    with pytest.raises(ValidationError):
        services.create_deck(user, "Čeština", foreign_language=cs, native_language=cs)


def test_child_takes_languages_from_parent(make_deck, es):
    english = make_deck("Angličtina")
    # Languages given for a child are ignored, the parent's are used
    child = services.create_deck(english.owner, "Seriály", parent=english, foreign_language=es)

    assert child.foreign_language == english.foreign_language
    assert child.native_language == english.native_language


def test_new_decks_go_to_the_end(make_deck):
    english = make_deck("Angličtina")
    first = make_deck("Seriály", parent=english)
    second = make_deck("Filmy", parent=english)

    assert first.position < second.position
    assert names(english.children.all()) == ["Seriály", "Filmy"]


def test_name_is_unique_under_one_parent_ignoring_case(make_deck):
    english = make_deck("Angličtina")
    make_deck("HIMYM", parent=english)

    with pytest.raises(ValidationError):
        make_deck("himym", parent=english)


def test_root_names_are_unique_too(make_deck):
    make_deck("Angličtina")

    with pytest.raises(ValidationError):
        make_deck("ANGLIČTINA")


def test_same_name_under_other_parent_is_fine(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    films = make_deck("Filmy", parent=english)

    make_deck("Oblíbené", parent=series)
    make_deck("Oblíbené", parent=films)


def test_other_user_can_use_the_same_name(make_deck, other_user):
    make_deck("Angličtina")
    make_deck("Angličtina", owner=other_user)


def test_cannot_add_child_to_other_users_deck(make_deck, other_user):
    english = make_deck("Angličtina")

    with pytest.raises(ValidationError):
        services.create_deck(other_user, "Seriály", parent=english)


def test_depth_is_limited_to_five(chain, make_deck):
    episode = chain[-1]

    assert services.get_depth(episode) == 5
    assert not services.can_add_child(episode)
    with pytest.raises(ValidationError):
        make_deck("Scéna 1", parent=episode)


# Reading


def test_ancestors_and_descendants(chain):
    english, series, himym, season, episode = chain

    assert names(services.get_ancestors(himym)) == ["Angličtina", "Seriály", "HIMYM"]
    assert set(services.get_descendant_ids(series)) == {
        series.pk,
        himym.pk,
        season.pk,
        episode.pk,
    }
    assert services.get_descendant_ids(episode, include_self=False) == []


def test_subtree_height(chain):
    english, series, himym, season, episode = chain

    assert services.get_subtree_height(english) == 5
    assert services.get_subtree_height(himym) == 3
    assert services.get_subtree_height(episode) == 1


def test_load_tree_uses_one_query(chain, make_deck, user, django_assert_num_queries):
    make_deck("Filmy", parent=chain[0])

    with django_assert_num_queries(1):
        roots = services.load_tree(user)
        # Language pair must not need more queries
        assert roots[0].language_pair == "EN → CS"

    english = roots[0]
    assert english.depth == 1
    assert names(english.tree_children) == ["Seriály", "Filmy"]
    assert english.tree_children[0].tree_children[0].depth == 3


def test_load_tree_shows_only_own_decks(make_deck, user, other_user):
    make_deck("Angličtina")
    make_deck("Cizí", owner=other_user)

    assert names(services.load_tree(user)) == ["Angličtina"]


# Moving


def test_move_deck_under_other_parent(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    films = make_deck("Filmy", parent=english)
    shrek = make_deck("Shrek", parent=series)

    services.move_deck(shrek, films)

    shrek.refresh_from_db()
    assert shrek.parent == films


def test_move_deck_to_top_level(chain):
    himym = chain[2]

    services.move_deck(himym, None)

    himym.refresh_from_db()
    assert himym.parent is None


def test_cannot_move_into_itself_or_child(chain):
    english, series, himym, season, episode = chain

    with pytest.raises(ValidationError):
        services.move_deck(series, series)
    with pytest.raises(ValidationError):
        services.move_deck(series, season)


def test_cannot_move_to_other_language_pair(make_deck, es, cs):
    english = make_deck("Angličtina")
    spanish = make_deck("Španělština", foreign=es, native=cs)
    series = make_deck("Seriály", parent=english)

    with pytest.raises(ValidationError):
        services.move_deck(series, spanish)


def test_cannot_move_when_tree_gets_too_deep(chain, make_deck):
    english, series, himym, season, episode = chain
    films = make_deck("Filmy", parent=english)
    # HIMYM has 3 levels (HIMYM, S01, E01); under Filmy (level 2) it would reach level 5: ok
    services.move_deck(himym, films)
    # Under S01 of another branch it would be too deep
    other = make_deck("Jiné", parent=films)
    deeper = make_deck("Hlubší", parent=other)

    with pytest.raises(ValidationError):
        services.move_deck(himym, deeper)


def test_cannot_move_when_name_exists_at_target(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    films = make_deck("Filmy", parent=english)
    make_deck("Oblíbené", parent=series)
    favourite_films = make_deck("Oblíbené", parent=films)

    with pytest.raises(ValidationError):
        services.move_deck(favourite_films, series)


def test_moved_deck_goes_to_the_end(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    films = make_deck("Filmy", parent=english)
    make_deck("HIMYM", parent=series)
    shrek = make_deck("Shrek", parent=films)

    services.move_deck(shrek, series)

    assert names(series.children.all()) == ["HIMYM", "Shrek"]


def test_move_targets(chain, make_deck, es, cs):
    english, series, himym, season, episode = chain
    films = make_deck("Filmy", parent=english)
    make_deck("Španělština", foreign=es, native=cs)

    targets = [deck for deck, _path in services.get_move_targets(himym)]

    # Own subtree is excluded, other language pair is excluded
    assert himym not in targets and season not in targets and episode not in targets
    assert all(deck.name != "Španělština" for deck in targets)
    # HIMYM has 3 levels, so the target can be at most on level 2
    assert set(names(targets)) == {"Angličtina", "Seriály", "Filmy"}
    assert films in targets


# Order


def test_move_up_and_down(make_deck):
    english = make_deck("Angličtina")
    a = make_deck("A", parent=english)
    make_deck("B", parent=english)
    c = make_deck("C", parent=english)

    services.move_deck_up(c)
    assert names(english.children.all()) == ["A", "C", "B"]

    services.move_deck_down(a)
    assert names(english.children.all()) == ["C", "A", "B"]


def test_move_up_at_the_top_does_nothing(make_deck):
    english = make_deck("Angličtina")
    a = make_deck("A", parent=english)
    b = make_deck("B", parent=english)

    services.move_deck_up(a)
    services.move_deck_down(b)

    assert names(english.children.all()) == ["A", "B"]


def test_root_decks_can_be_ordered(make_deck, es, cs):
    make_deck("Angličtina")
    spanish = make_deck("Španělština", foreign=es, native=cs)

    services.move_deck_up(spanish)

    assert names(Deck.objects.filter(parent=None)) == ["Španělština", "Angličtina"]


# Deleting


def test_delete_deck_with_children(chain):
    english, series, himym, season, episode = chain

    deck_count, term_count = services.delete_deck(series)

    assert (deck_count, term_count) == (4, 0)
    assert names(Deck.objects.all()) == ["Angličtina"]


# Drag and drop: place_deck


def test_place_deck_into_deck_without_children(make_deck):
    english = make_deck("CzechEnglish")
    series = make_deck("series", parent=english)
    show = make_deck("Two and half men", parent=english)

    services.place_deck(show, series, 0)

    show.refresh_from_db()
    assert show.parent == series


def test_place_deck_changes_order(make_deck):
    english = make_deck("Angličtina")
    for name in ["A", "B", "C"]:
        make_deck(name, parent=english)
    c = Deck.objects.get(name="C")

    services.place_deck(c, english, 0)

    assert names(english.children.all()) == ["C", "A", "B"]


def test_place_deck_at_index_in_other_folder(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)
    make_deck("A", parent=series)
    make_deck("B", parent=series)
    films = make_deck("Filmy", parent=english)
    shrek = make_deck("Shrek", parent=films)

    services.place_deck(shrek, series, 1)

    assert names(series.children.all()) == ["A", "Shrek", "B"]


def test_place_deck_to_top_level(make_deck):
    english = make_deck("Angličtina")
    series = make_deck("Seriály", parent=english)

    services.place_deck(series, None, 0)

    assert names(Deck.objects.filter(parent=None)) == ["Seriály", "Angličtina"]


def test_place_deck_index_out_of_range_goes_to_the_end(make_deck):
    english = make_deck("Angličtina")
    make_deck("A", parent=english)
    b = make_deck("B", parent=english)

    services.place_deck(b, english, 99)
    services.place_deck(b, english, -5)

    assert names(english.children.all()) == ["B", "A"]


def test_place_deck_keeps_the_rules(chain, make_deck, es, cs):
    english, series, himym, season, episode = chain
    spanish = make_deck("Španělština", foreign=es, native=cs)
    make_deck("S01", parent=series)

    with pytest.raises(ValidationError):
        services.place_deck(series, episode, 0)  # into its own child
    with pytest.raises(ValidationError):
        services.place_deck(himym, spanish, 0)  # other language pair
    with pytest.raises(ValidationError):
        services.place_deck(english, episode, 0)  # too deep and a cycle
    with pytest.raises(ValidationError):
        services.place_deck(season, series, 0)  # "S01" exists there already
    season.refresh_from_db()
    assert season.parent == himym
