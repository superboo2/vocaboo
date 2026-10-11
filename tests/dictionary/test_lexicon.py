"""The dictionary of the app: import, translation suggestions, other meanings on the word page."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from dictionary.models import LexiconEntry, LexiconSense, LexiconTag
from dictionary.providers import get_suggestions
from tests.conftest import lexicon_entry
from vocabulary import services
from vocabulary.models import Term

PRESENT = [
    lexicon_entry(
        "present",
        "noun",
        [
            ("dárek", "Thanks for the {present}!", "Díky za {dárek}!"),
            ("současnost", "Live in the {present}.", "Žij v {současnosti}."),
        ],
        band=2,
    ),
    lexicon_entry(
        "present",
        "verb",
        [
            (
                "představit; představovat",
                "Let me {present} my wife.",
                "Dovolte, abych vám {představil} manželku.",
            )
        ],
        band=4,
    ),
]
PALM = lexicon_entry(
    "palm",
    "noun",
    [
        ("dlaň", "She read my {palm}.", "Četla mi z {dlaně}."),
        ("palma", "A {palm} on the beach.", "{Palma} na pláži.", "strom", ["rostlina"]),
    ],
    band=5,
    ipa="pɑːm",
)
MOM = lexicon_entry("mom", "noun", [("máma", "Call your {mom}.", "Zavolej {mámě}.")], forms=["mum"])


@pytest.fixture
def imported(lexicon):
    return lexicon(*PRESENT, PALM, MOM)


# Import


def test_import(imported):
    assert LexiconEntry.objects.count() == 4
    palm = LexiconEntry.objects.get(word="palm")
    assert (palm.band, palm.ipa, palm.part_of_speech) == (5, "pɑːm", "noun")
    tree = palm.senses.get(position=1)
    assert (tree.translation, tree.note, tree.sentence_native) == (
        "palma",
        "strom",
        "{Palma} na pláži.",
    )
    assert list(tree.tags.values_list("slug", flat=True)) == ["rostlina"]
    assert sorted(LexiconEntry.objects.get(word="mom").forms.values_list("text", flat=True)) == [
        "mom",
        "mum",
    ]


def test_import_again_replaces_data(imported, lexicon):
    lexicon(PALM)

    assert LexiconEntry.objects.count() == 1
    assert LexiconSense.objects.count() == 2
    assert LexiconTag.objects.count() == 1


def test_import_refuses_unknown_tag(lexicon):
    bad = lexicon_entry("tree", "noun", [("strom", "A {tree}.", "Strom.", "", ["neznamy"])])

    with pytest.raises(CommandError):
        lexicon(bad)
    # Nothing is half imported
    assert LexiconEntry.objects.count() == 0


def test_import_needs_existing_file(db, tmp_path):
    with pytest.raises(CommandError):
        call_command("import_lexicon", str(tmp_path / "missing.jsonl"))


# Suggestions


def test_suggestions_for_word_with_more_meanings(imported):
    result = get_suggestions("Present", "en", "cs")

    # The more common entry first, inside it the more common meaning first
    assert [(s.translation, s.part_of_speech) for s in result.suggestions] == [
        ("dárek", "noun"),
        ("současnost", "noun"),
        ("představit; představovat", "verb"),
    ]
    assert result.suggestions[2].short_pos == "slov."
    assert result.suggestions[0].examples == [
        {"text": "Thanks for the {present}!", "translation": "Díky za {dárek}!"}
    ]


def test_suggestions_by_other_spelling_and_first_variant(imported):
    assert get_suggestions("mum", "en", "cs").suggestions[0].translation == "máma"
    assert [s.translation for s in get_suggestions("palm; palm tree", "en", "cs").suggestions] == [
        "dlaň",
        "palma",
    ]


def test_no_suggestions(imported, settings):
    assert get_suggestions("unknownword", "en", "cs") is None
    assert get_suggestions("", "en", "cs") is None
    # The dictionary is English–Czech only
    assert get_suggestions("palm", "en", "de") is None
    settings.SUGGESTION_PROVIDERS = []
    assert get_suggestions("palm", "en", "cs") is None


# The word form


@pytest.fixture
def deck(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


def test_suggest_view(client, user, deck, imported):
    client.force_login(user)

    url = reverse("vocabulary:term_suggest", args=[deck.pk])
    html = client.get(url, {"foreign": "palm"}, headers={"HX-Request": "true"}).content.decode()

    assert 'data-translation="palma"' in html
    assert 'data-translation="dlaň"' in html
    assert 'id="term-suggest"' in html
    # No source is named
    assert "suggest-source" not in html


def test_suggest_view_for_unknown_word_is_empty(client, user, deck, imported):
    client.force_login(user)

    url = reverse("vocabulary:term_suggest", args=[deck.pk])
    html = client.get(url, {"foreign": "zzz"}).content.decode()

    assert 'id="term-suggest"' in html
    assert "data-translation" not in html


def test_suggest_view_for_other_users_deck(client, other_user, deck, imported):
    client.force_login(other_user)

    url = reverse("vocabulary:term_suggest", args=[deck.pk])
    assert client.get(url, {"foreign": "palm"}).status_code == 404


def test_word_form_has_suggestion_area(client, user, deck):
    client.force_login(user)

    html = client.get(reverse("vocabulary:deck_detail", args=[deck.pk])).content.decode()

    assert 'id="term-suggest"' in html


def test_suggestions_turned_off_in_settings(client, user, deck, imported):
    user.show_suggestions = False
    user.save()
    client.force_login(user)

    form_html = client.get(reverse("vocabulary:deck_detail", args=[deck.pk])).content.decode()
    url = reverse("vocabulary:term_suggest", args=[deck.pk])
    suggest_html = client.get(url, {"foreign": "palm"}).content.decode()

    assert 'id="term-suggest"' not in form_html
    assert "data-translation" not in suggest_html


# Other meanings on the word page


def test_word_page_shows_other_meanings(client, user, deck, imported):
    item = services.add_term(deck, foreign="present", native="dárek")
    services.add_term(deck, foreign="present", native="současnost")
    client.force_login(user)

    url = reverse("vocabulary:term_detail", args=[deck.pk, item.pk])
    html = client.get(url).content.decode()

    assert "Další významy" in html
    # The own other word is marked, the dictionary meaning can be added
    assert "<strong>současnost</strong>" in html
    assert 'value="představit; představovat"' in html
    assert "Učit se i tento význam" in html
    # The meaning of this word itself is not offered again
    assert 'value="dárek"' not in html
    assert "Wiktionary" not in html


def test_add_other_meaning_from_word_page(client, user, deck, imported):
    item = services.add_term(deck, foreign="present", native="dárek")
    client.force_login(user)

    url = reverse("vocabulary:term_add_meaning", args=[deck.pk, item.pk])
    response = client.post(url, {"translation": "představit; představovat"})

    assert response.url == reverse("vocabulary:term_detail", args=[deck.pk, item.pk])
    new = Term.objects.get(main_native="představit")
    assert new.native_variants == ["představit", "představovat"]
    assert new.deck_terms.get().deck == deck


def test_add_other_meaning_twice_is_refused(client, user, deck, imported):
    item = services.add_term(deck, foreign="present", native="dárek")
    client.force_login(user)
    url = reverse("vocabulary:term_add_meaning", args=[deck.pk, item.pk])

    client.post(url, {"translation": "současnost"})
    client.post(url, {"translation": "současnost"})

    assert Term.objects.filter(main_native="současnost").count() == 1


def test_add_other_meaning_needs_post_and_own_word(client, other_user, deck, imported):
    item = services.add_term(deck, foreign="present", native="dárek")
    client.force_login(other_user)
    url = reverse("vocabulary:term_add_meaning", args=[deck.pk, item.pk])

    assert client.get(url).status_code == 405
    assert client.post(url, {"translation": "současnost"}).status_code == 404
