"""Shared pytest fixtures for all apps."""

import io
import json

import pytest
from django.contrib.auth import get_user_model

from vocabulary.models import Language


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    # Real password hashing is slow on purpose; tests do not need it
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def czech_by_default(settings):
    # The tests check the Czech texts; without a browser language the app would be English
    settings.LANGUAGE_CODE = "cs"


@pytest.fixture(autouse=True)
def plain_static_files(settings):
    # Tests do not run collectstatic, so static files keep their plain names
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        email="martin@example.com", password="secret-pass-123"
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        email="other@example.com", password="secret-pass-123"
    )


@pytest.fixture
def cs(db):
    return Language.objects.get(code="cs")


@pytest.fixture
def en(db):
    return Language.objects.get(code="en")


@pytest.fixture
def es(db):
    return Language.objects.get(code="es")


def lexicon_entry(word, pos, senses, band=1, ipa="", forms=()):
    """A word with its meanings for the fixture lexicon; a sense is
    (cs, sentence, sentence_cs[, note, tags]) and becomes the concept word.pos.number."""
    return {
        "word": word,
        "pos": pos,
        "band": band,
        "level": "A1",
        "ipa": ipa or word,
        "forms": list(forms),
        "senses": [
            {
                "cs": sense[0],
                "sentence": sense[1],
                "sentence_cs": sense[2],
                "note": sense[3] if len(sense) > 3 else "",
                "tags": sense[4] if len(sense) > 4 else [],
            }
            for sense in senses
        ],
    }


@pytest.fixture
def lexicon(db, tmp_path):
    """Import dictionary entries into the database with the real command import_lexicon.

    The entries are in the short form of lexicon_entry (a word with its meanings); they are
    written as the files of the app (concepts.jsonl, words_en.jsonl) and imported.
    """
    from django.core.management import call_command

    from dictionary import lexicon_files

    def load(*entries, tags=({"slug": "rostlina", "name": "rostliny", "parent": None},)):
        folder = tmp_path / "lexicon"
        concepts, words = lexicon_files.convert_old(entries)
        lexicon_files.write_layer(folder, concepts, {"en": words})
        (folder / "lexicon_tags.json").write_text(json.dumps(list(tags)), encoding="utf-8")
        call_command("import_lexicon", "--data", str(folder), stdout=io.StringIO())
        return folder

    return load
