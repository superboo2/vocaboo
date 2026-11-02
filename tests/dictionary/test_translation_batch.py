"""The command translation_batch: the next concepts to translate into a new language."""

from dictionary.lexicon_files import Layer
from dictionary.management.commands.translation_batch import next_batch


def concept(key, **texts):
    return {"id": key, "texts": texts}


def word(text, band, senses):
    return {"word": text, "pos": "noun", "band": band, "level": "A1", "senses": senses}


BASE = Layer(
    name="data",
    source="base",
    concepts=[
        concept(
            "palm.noun.1",
            en={"words": "palm", "sentence": "She read my {palm}."},
            cs={"words": "dlaň", "note": "", "sentence": "Četla mi z {dlaně}."},
        ),
        concept(
            "palm.noun.2",
            en={"words": "palm", "sentence": "A {palm} on the beach."},
            cs={"words": "palma", "note": "strom", "sentence": ""},
        ),
        concept(
            "cat.noun.1",
            en={"words": "cat", "sentence": "The {cat} sleeps."},
            cs={"words": "kočka; kocour", "note": ""},
        ),
    ],
    words={"en": [word("palm", 5, ["palm.noun.1", "palm.noun.2"]), word("cat", 1, ["cat.noun.1"])]},
)
# A package that already translated one meaning of palm
PACKAGE = Layer(
    name="2026-11-02",
    source="2026-11-02",
    concepts=[concept("palm.noun.1", uk={"words": "долоня", "sentence": "По {долоні}."})],
)


def test_most_common_first_and_only_untranslated():
    batch = next_batch([BASE, PACKAGE], "uk", 10)

    assert [item["id"] for item in batch] == ["cat.noun.1", "palm.noun.2"]
    assert batch[0] == {
        "id": "cat.noun.1",
        "en": {"words": "cat", "sentence": "The {cat} sleeps."},
        "cs": {"words": "kočka; kocour", "note": ""},
    }
    assert batch[1]["cs"]["note"] == "strom"


def test_count_limits_the_batch():
    assert [item["id"] for item in next_batch([BASE], "uk", 2)] == ["cat.noun.1", "palm.noun.1"]


def test_a_translated_language_has_nothing_left():
    assert next_batch([BASE], "cs", 10) == []
