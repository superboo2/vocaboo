"""Packages of new words for the dictionary: extend_lexicon and import_lexicon with packages."""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from dictionary import lexicon_files
from dictionary.models import Concept, LexiconWord
from dictionary.providers import get_suggestions
from tests.conftest import lexicon_entry

TAGS = [{"slug": "rostlina", "name": "rostliny", "parent": None}]
PALM = lexicon_entry("palm", "noun", [("dlaň", "She read my {palm}.", "Četla mi z {dlaně}.")])
KID = lexicon_entry("kid", "noun", [("dítě", "The {kid} is asleep.", "{Dítě} spí.")])
OGRE_CONCEPT = {
    "id": "ogre.noun.1",
    "texts": {
        "en": {"words": "ogre", "sentence": "{Ogres} are like onions."},
        "cs": {"words": "zlobr", "sentence": "{Zlobři} jsou jako cibule."},
    },
}
OGRE = {"word": "ogre", "pos": "noun", "band": 12, "level": "B2", "senses": ["ogre.noun.1"]}


@pytest.fixture
def data(tmp_path, monkeypatch, db):
    """A data folder with the base (palm, kid) and the tags, used by both commands."""
    monkeypatch.setattr(lexicon_files, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lexicon_files, "TAGS_FILE", tmp_path / "lexicon_tags.json")
    monkeypatch.setattr(lexicon_files, "EXTENSIONS_DIR", tmp_path / "extensions")
    concepts, words = lexicon_files.convert_old([PALM, KID])
    lexicon_files.write_layer(tmp_path, concepts, {"en": words})
    (tmp_path / "lexicon_tags.json").write_text(json.dumps(TAGS), encoding="utf-8")
    call_command("import_lexicon", stdout=io.StringIO())
    return tmp_path


def package(data, name, concepts=(), words=None, report=None):
    folder = data / "extensions" / name
    lexicon_files.write_layer(folder, list(concepts), words or {})
    if report:
        (folder / "report.txt").write_text(report, encoding="utf-8")
    return folder


def extend(folder, *args):
    out = io.StringIO()
    call_command("extend_lexicon", str(folder), *args, stdout=out)
    return out.getvalue()


def test_package_adds_words_and_replaces_the_same_word(data):
    kid = {**json.loads((data / "words_en.jsonl").read_text().splitlines()[1]), "forms": ["kids"]}
    folder = package(data, "2026-11-02", [OGRE_CONCEPT], {"en": [OGRE, kid]})

    out = extend(folder)

    assert "concepts added 1, changed 0; words added 1, changed 1" in out
    assert Concept.objects.get(key="ogre.noun.1").source == "2026-11-02"
    word = LexiconWord.objects.get(word="kid")
    assert word.source == "2026-11-02"
    assert sorted(word.forms.values_list("text", flat=True)) == ["kid", "kids"]
    assert get_suggestions("ogres", "en", "cs") is None
    assert [s.translation for s in get_suggestions("ogre", "en", "cs").suggestions] == ["zlobr"]
    # The rest stays as it was; running it again changes nothing
    assert LexiconWord.objects.get(word="palm").source == "base"
    extend(folder)
    assert (Concept.objects.count(), LexiconWord.objects.count()) == (3, 3)


def test_package_adds_a_language_to_known_concepts(data):
    # Spanish texts for the palm only: Czech stays, EN → ES has a suggestion now
    spanish = {"id": "palm.noun.1", "texts": {"es": {"words": "palma", "sentence": "La {palma}."}}}
    folder = package(data, "2026-11-02", [spanish])

    extend(folder)

    assert [s.translation for s in get_suggestions("palm", "en", "es").suggestions] == ["palma"]
    assert [s.translation for s in get_suggestions("palm", "en", "cs").suggestions] == ["dlaň"]
    assert get_suggestions("kid", "en", "es") is None
    # Every pair with Spanish works at once: ES → CS and CS → ES go through the concept
    assert [s.translation for s in get_suggestions("palma", "es", "cs").suggestions] == ["dlaň"]
    assert [s.translation for s in get_suggestions("dlaň", "cs", "es").suggestions] == ["palma"]


def test_package_with_a_mistake_writes_nothing(data):
    broken = {**OGRE_CONCEPT, "texts": {"en": {"words": "ogre", "sentence": "No braces."}}}
    folder = package(
        data,
        "2026-11-02",
        [broken],
        {"en": [{**OGRE, "level": "D1"}, {**OGRE, "word": "troll", "senses": ["troll.noun.1"]}]},
    )

    with pytest.raises(CommandError) as error:
        extend(folder)

    message = str(error.value)
    assert "no {word} in the sentence" in message
    assert "level must be one of" in message
    assert "unknown concepts troll.noun.1" in message
    assert not Concept.objects.filter(key="ogre.noun.1").exists()


def test_check_only_and_the_report(data):
    report = "changed  ogres → ogre (plural, form added)\nskipped  wep (unclear word)\n"
    folder = package(data, "2026-11-02", [OGRE_CONCEPT], {"en": [OGRE]}, report=report)

    out = extend(folder, "--check")

    assert out.startswith("changed  ogres → ogre (plural, form added)\nskipped  wep (unclear word)")
    assert "OK: 1 concepts, 1 words" in out
    assert not Concept.objects.filter(key="ogre.noun.1").exists()


def test_package_needs_a_date_name(data):
    with pytest.raises(CommandError):
        extend(package(data, "new-words", [OGRE_CONCEPT], {"en": [OGRE]}))


def test_full_import_reads_the_base_and_all_packages_in_order(data):
    package(data, "2026-11-02", [OGRE_CONCEPT], {"en": [OGRE]})
    package(data, "2026-11-16", [], {"en": [{**OGRE, "band": 10}]})
    LexiconWord.objects.all().delete()

    out = io.StringIO()
    call_command("import_lexicon", stdout=out)

    assert "Imported 3 concepts and 3 words (en)" in out.getvalue()
    assert "2 packages" in out.getvalue()
    # The later package wins
    ogre = LexiconWord.objects.get(word="ogre")
    assert (ogre.band, ogre.source) == (10, "2026-11-16")
