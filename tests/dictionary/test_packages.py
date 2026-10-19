"""Packages of new words for the dictionary: extend_lexicon and import_lexicon with packages."""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from dictionary import lexicon_files
from dictionary.models import LexiconEntry
from tests.conftest import lexicon_entry

TAGS = [{"slug": "rostlina", "name": "rostliny", "parent": None}]
PALM = lexicon_entry("palm", "noun", [("dlaň", "She read my {palm}.", "Četla mi z {dlaně}.")])
KID = lexicon_entry("kid", "noun", [("dítě", "The {kid} is asleep.", "{Dítě} spí.")])
OGRE = lexicon_entry("ogre", "noun", [("zlobr", "{Ogres} are like onions.", "Zlobři.")], band=12)


@pytest.fixture
def data(tmp_path, monkeypatch, db):
    """A data folder with the base (palm, kid) and the tags, used by both commands."""
    monkeypatch.setattr(lexicon_files, "BASE_FILE", tmp_path / "lexicon_en_cs.jsonl")
    monkeypatch.setattr(lexicon_files, "TAGS_FILE", tmp_path / "lexicon_tags.json")
    monkeypatch.setattr(lexicon_files, "EXTENSIONS_DIR", tmp_path / "extensions")
    write(tmp_path / "lexicon_en_cs.jsonl", PALM, KID)
    (tmp_path / "lexicon_tags.json").write_text(json.dumps(TAGS), encoding="utf-8")
    (tmp_path / "extensions").mkdir()
    call_command("import_lexicon", stdout=io.StringIO())
    return tmp_path


def write(path, *entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def extend(path, *args):
    out = io.StringIO()
    call_command("extend_lexicon", str(path), *args, stdout=out)
    return out.getvalue()


def test_package_adds_words_and_replaces_the_same_entry(data):
    # A new word, and "kid" again with the form "kids"
    package = write(data / "extensions" / "2026-10-19.jsonl", OGRE, {**KID, "forms": ["kids"]})

    out = extend(package)

    assert "Package 2026-10-19: added 1 entries, changed 1" in out
    assert LexiconEntry.objects.get(word="ogre").source == "2026-10-19"
    kid = LexiconEntry.objects.get(word="kid")
    assert kid.source == "2026-10-19"
    assert sorted(kid.forms.values_list("text", flat=True)) == ["kid", "kids"]
    # The rest stays as it was
    assert LexiconEntry.objects.get(word="palm").source == "base"
    # Running it again changes nothing
    extend(package)
    assert LexiconEntry.objects.count() == 3


def test_package_with_a_mistake_writes_nothing(data):
    broken = {**OGRE, "senses": [{**OGRE["senses"][0], "sentence": "No braces here."}]}
    package = write(data / "extensions" / "2026-10-19.jsonl", broken, {**KID, "level": "D1"})

    with pytest.raises(CommandError) as error:
        extend(package)

    assert "no {word} in the sentence" in str(error.value)
    assert "level must be one of" in str(error.value)
    assert not LexiconEntry.objects.filter(word="ogre").exists()


def test_check_only(data):
    package = write(data / "extensions" / "2026-10-19.jsonl", OGRE)

    assert "OK: 1 entries" in extend(package, "--check")
    assert not LexiconEntry.objects.filter(word="ogre").exists()


def test_package_needs_a_date_name(data):
    with pytest.raises(CommandError):
        extend(write(data / "extensions" / "new-words.jsonl", OGRE))


def test_full_import_reads_the_base_and_all_packages_in_order(data):
    write(data / "extensions" / "2026-10-19.jsonl", OGRE)
    write(data / "extensions" / "2026-11-16.jsonl", {**OGRE, "band": 10})
    LexiconEntry.objects.all().delete()

    out = io.StringIO()
    call_command("import_lexicon", stdout=out)

    assert "Imported 3 entries" in out.getvalue()
    assert "2 packages" in out.getvalue()
    # The later package wins
    ogre = LexiconEntry.objects.get(word="ogre")
    assert (ogre.band, ogre.source) == (10, "2026-11-16")


def test_report_of_the_package_is_printed(data):
    package = write(data / "extensions" / "2026-10-19.jsonl", OGRE, {**KID, "forms": ["kids"]})
    report = "changed  kids → kid (plural, form added)\nskipped  wep (unclear word)\n"
    (data / "extensions" / "2026-10-19.report.txt").write_text(report, encoding="utf-8")

    out = extend(package, "--check")

    assert out.startswith("changed  kids → kid (plural, form added)\nskipped  wep (unclear word)")
