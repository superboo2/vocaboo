"""Translation suggestions from the imported Czech Wiktionary."""

import gzip
import json

import pytest
from django.core.management import call_command
from django.urls import reverse

from dictionary.models import DictionaryEntry
from dictionary.providers import get_suggestions, split_gloss
from vocabulary import services
from vocabulary.models import Term

LINES = [
    {
        "word": "present",
        "lang_code": "en",
        "pos": "noun",
        "pos_title": "podstatné jméno",
        "senses": [{"glosses": ["současnost"]}, {"glosses": ["dárek"]}],
        "sounds": [{"ipa": "[ˈprɛzənt]"}],
    },
    {
        "word": "present",
        "lang_code": "en",
        "pos": "verb",
        "pos_title": "sloveso",
        "senses": [
            {
                "glosses": ["představit, představovat"],
                "examples": [
                    {
                        "text": "Let me present my wife.",
                        "translation": "Dovolte, abych vám představil svou ženu.",
                    }
                ],
            }
        ],
    },
    {
        "word": "palm",
        "lang_code": "en",
        "pos_title": "podstatné jméno",
        "senses": [{"glosses": ["palma"]}, {"glosses": ["dlaň"]}],
        "sounds": [{"audio": "En-us-palm.ogg", "mp3_url": "https://example.org/palm.mp3"}],
    },
    {
        "word": "hola",
        "lang_code": "es",
        "pos_title": "citoslovce",
        "senses": [{"glosses": ["ahoj"]}],
    },
    # Czech words, entries without meanings and broken codes are skipped
    {"word": "pes", "lang_code": "cs", "senses": [{"glosses": ["savec"]}]},
    {"word": "empty", "lang_code": "en", "senses": [{"glosses": []}]},
    {"word": "odd", "lang_code": "", "senses": [{"glosses": ["x"]}]},
]


@pytest.fixture
def wiktionary_file(tmp_path):
    path = tmp_path / "cs-extract.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as file:
        for line in LINES:
            file.write(json.dumps(line, ensure_ascii=False) + "\n")
    return str(path)


@pytest.fixture
def imported(db, wiktionary_file):
    call_command("import_wiktionary", wiktionary_file)


# Import


def test_import(imported):
    assert DictionaryEntry.objects.count() == 4
    verb = DictionaryEntry.objects.get(word="present", part_of_speech="sloveso")
    assert verb.senses == [
        {
            "text": "představit, představovat",
            "examples": [
                {
                    "text": "Let me present my wife.",
                    "translation": "Dovolte, abych vám představil svou ženu.",
                }
            ],
        }
    ]
    palm = DictionaryEntry.objects.get(word="palm")
    assert palm.audio_url == "https://example.org/palm.mp3"
    assert DictionaryEntry.objects.get(word="present", part_of_speech="podstatné jméno").ipa


def test_import_again_replaces_data(imported, wiktionary_file):
    call_command("import_wiktionary", wiktionary_file)

    assert DictionaryEntry.objects.count() == 4


def test_import_only_some_languages(db, wiktionary_file, capsys):
    call_command("import_wiktionary", wiktionary_file, languages="es")

    assert list(DictionaryEntry.objects.values_list("word", flat=True)) == ["hola"]
    assert "Imported 1 entries" in capsys.readouterr().out


def test_import_also_reads_plain_jsonl(db, tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(json.dumps(LINES[3]) + "\n", encoding="utf-8")

    call_command("import_wiktionary", str(path))

    assert DictionaryEntry.objects.get().word == "hola"


# Glosses


@pytest.mark.parametrize(
    ("gloss", "expected"),
    [
        ("dárek", ("dárek", "")),
        ("dosavadní, současný, nynější", ("dosavadní; současný; nynější", "")),
        ("(o dopravě) jezdit, obsluhovat", ("jezdit; obsluhovat", "o dopravě")),
        ("run (na banku)", ("run", "na banku")),
        ("doba kdy jeden tým několikrát po sobě skóruje", ("", "")),
    ],
)
def test_split_gloss(gloss, expected):
    assert split_gloss(gloss) == expected


# Suggestions


def test_suggestions_for_word_with_more_meanings(imported):
    result = get_suggestions("Present", "en", "cs")

    assert [(s.translation, s.part_of_speech) for s in result.suggestions] == [
        ("současnost", "podstatné jméno"),
        ("dárek", "podstatné jméno"),
        ("představit; představovat", "sloveso"),
    ]
    assert result.suggestions[2].examples == [
        {
            "text": "Let me present my wife.",
            "translation": "Dovolte, abych vám představil svou ženu.",
        }
    ]
    assert result.source_name.startswith("Wiktionary")
    assert result.source_url == "https://cs.wiktionary.org/wiki/present"


def test_suggestions_use_the_first_variant(imported):
    result = get_suggestions("palm; palm tree", "en", "cs")

    assert [s.translation for s in result.suggestions] == ["palma", "dlaň"]


def test_no_suggestions(imported):
    assert get_suggestions("unknownword", "en", "cs") is None
    assert get_suggestions("", "en", "cs") is None
    # The data has only Czech meanings
    assert get_suggestions("palm", "en", "de") is None


def test_no_suggestions_without_providers(imported, settings):
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
    assert "cs.wiktionary.org/wiki/palm" in html
    assert 'id="term-suggest"' in html


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
