"""The command missing_words: English words of the decks that the dictionary does not know."""

import io

import pytest
from django.core.management import call_command

from tests.conftest import lexicon_entry
from vocabulary import services

PALM = lexicon_entry("palm", "noun", [("dlaň", "She read my {palm}.", "Četla mi z {dlaně}.")])
MOM = lexicon_entry("mom", "noun", [("máma", "Call your {mom}.", "Zavolej {mámě}.")], forms=["mum"])


@pytest.fixture
def decks(lexicon, user, other_user, en, cs, es):
    lexicon(PALM, MOM)
    english = services.create_deck(user, "Seriály", foreign_language=en, native_language=cs)
    services.add_term(english, foreign="palm", native="dlaň")
    # "mum" is another spelling of an entry, so it is known
    services.add_term(english, foreign="mum", native="máma")
    services.add_term(english, foreign="fella; bloke", native="chlápek")
    services.add_term(english, foreign="R2", native="robot")
    # Another user has the same word: it is listed once
    theirs = services.create_deck(other_user, "Mine", foreign_language=en, native_language=cs)
    services.add_term(theirs, foreign="Fella", native="kámoš")
    # Other languages are not checked (no hints for them), nor English translations
    czech = services.create_deck(other_user, "Czech", foreign_language=cs, native_language=en)
    services.add_term(czech, foreign="hospoda", native="pub")
    spanish = services.create_deck(user, "Español", foreign_language=es, native_language=cs)
    services.add_term(spanish, foreign="hola", native="ahoj")


def test_lists_unknown_english_words_once(decks):
    out = io.StringIO()
    call_command("missing_words", stdout=out)

    assert out.getvalue().splitlines() == ["bloke", "fella"]


def test_writes_the_list_to_a_file(decks, tmp_path):
    path = tmp_path / "missing.txt"

    call_command("missing_words", "--output", str(path), stdout=io.StringIO())

    assert path.read_text(encoding="utf-8") == "bloke\nfella\n"
