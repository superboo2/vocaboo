"""Files of the dictionary of the app: read, check and save into the database.

The dictionary is files, the database is only a copy for fast lookups (docs/slovnik.md):

    dictionary/data/
      concepts.jsonl          concepts (meanings) with their texts in each language
      words_en.jsonl          English words, each pointing to its concepts
      lexicon_tags.json       the tags of the concepts
      extensions/2026-11-02/  a package of new words: concepts.jsonl, words_*.jsonl, report.txt

A concept line:  {"id": "palm.noun.1", "tags": ["telo"],
                  "texts": {"en": {"words": "palm", "sentence": "She read my {palm}."},
                            "cs": {"words": "dlaň", "note": "", "sentence": "Četla mi z {dlaně}."}}}
A word line:     {"word": "palm", "pos": "noun", "band": 5, "level": "B1", "ipa": "pɑːm",
                  "forms": ["palms"], "senses": ["palm.noun.1", "palm.noun.2"]}

A later layer (a package) adds concepts and words; a concept with a known id gets the texts of
the languages the package has (the other languages stay) and its tags when they are given; a
word with the same language, word and part of speech is replaced.
"""

import json
import pathlib
import re
from dataclasses import dataclass, field

from django.conf import settings

from .models import (
    Concept,
    ConceptText,
    ConceptTextForm,
    LexiconTag,
    LexiconWord,
    PartOfSpeech,
    WordForm,
    WordSense,
)

DATA_DIR = pathlib.Path(settings.BASE_DIR) / "dictionary" / "data"
TAGS_FILE = DATA_DIR / "lexicon_tags.json"
EXTENSIONS_DIR = DATA_DIR / "extensions"
CONCEPTS_FILE = "concepts.jsonl"
WORDS_FILE = re.compile(r"^words_([a-z]{2})\.jsonl$")
REPORT_FILE = "report.txt"
BASE_SOURCE = "base"
# A package is named by the day it was made, e.g. 2026-11-02 (so the names sort by date)
PACKAGE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}(-\d+)?$")
# word.part_of_speech.number, e.g. "palm.noun.1", "suit up.phrasal_verb.1"
CONCEPT_KEY = re.compile(r"^\S(.*\S)?\.[a-z_]+\.\d+$")
LANGUAGE = re.compile(r"^[a-z]{2}$")
# The concepts are defined by their English sentence
DEFINING_LANGUAGE = "en"
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
WORD_FIELDS = ("word", "pos", "band", "level", "senses")
BATCH = 2000


class LexiconFileError(Exception):
    """The files cannot be imported; the message says where and why."""


@dataclass
class Layer:
    """The base or one package: its concepts and its words by language."""

    name: str
    source: str
    concepts: list = field(default_factory=list)
    words: dict = field(default_factory=dict)


def read_jsonl(path):
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise LexiconFileError(f"{path.name}:{number}: bad JSON: {error}") from error
    return items


def read_layer(folder, source):
    """The concepts and words of a folder (the base data folder or a package)."""
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        raise LexiconFileError(f"Folder not found: {folder}")
    layer = Layer(name=folder.name, source=source)
    if (folder / CONCEPTS_FILE).exists():
        layer.concepts = read_jsonl(folder / CONCEPTS_FILE)
    for path in sorted(folder.iterdir()):
        match = WORDS_FILE.match(path.name)
        if match:
            layer.words[match.group(1)] = read_jsonl(path)
    if not layer.concepts and not layer.words:
        raise LexiconFileError(f"No {CONCEPTS_FILE} or words_<language>.jsonl in {folder}")
    return layer


def read_tags(path=TAGS_FILE):
    path = pathlib.Path(path)
    if not path.exists():
        raise LexiconFileError(f"Tags file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LexiconFileError(f"{path.name}: bad JSON: {error}") from error


def package_folders():
    """The packages of new words, the oldest first."""
    if not EXTENSIONS_DIR.exists():
        return []
    return sorted(
        path for path in EXTENSIONS_DIR.iterdir() if path.is_dir() and PACKAGE_NAME.match(path.name)
    )


def check(layer, tag_slugs, known_keys):
    """All mistakes of a layer as texts like "2026-11-02/concepts:3 ogre.noun.1: …".

    known_keys are the concept keys that exist before this layer (earlier layers or the
    database); a new concept needs its English sentence, which defines it.
    """
    problems = []
    keys = set()
    for number, item in enumerate(layer.concepts, start=1):
        key = item.get("id", "")
        where = f"{layer.name}/concepts:{number} {key or '?'}"
        if not isinstance(key, str) or not CONCEPT_KEY.match(key):
            problems.append(f"{where}: the id must look like word.part_of_speech.number")
            continue
        if key in keys:
            problems.append(f"{where}: twice in the file")
        keys.add(key)
        unknown = [slug for slug in item.get("tags", []) if slug not in tag_slugs]
        if unknown:
            problems.append(f"{where}: unknown tags {', '.join(unknown)}")
        texts = item.get("texts", {})
        if not isinstance(texts, dict) or (not texts and key not in known_keys):
            problems.append(f"{where}: no texts")
            continue
        for language, text in texts.items():
            if not LANGUAGE.match(language):
                problems.append(f"{where}: bad language code {language!r}")
            elif not isinstance(text, dict) or not str(text.get("words", "")).strip():
                problems.append(f"{where}: no words in {language}")
        defining = texts.get(DEFINING_LANGUAGE, {})
        sentence = defining.get("sentence", "") if isinstance(defining, dict) else ""
        if key not in known_keys and not sentence:
            problems.append(f"{where}: a new concept needs its {DEFINING_LANGUAGE} sentence")
        if sentence and not re.search(r"\{[^{}]+\}", sentence):
            problems.append(f"{where}: no {{word}} in the sentence {sentence!r}")

    available = known_keys | keys
    parts_of_speech = set(PartOfSpeech.values)
    for language, words in layer.words.items():
        seen = set()
        for number, item in enumerate(words, start=1):
            where = f"{layer.name}/words_{language}:{number} {item.get('word', '?')}"
            missing = [name for name in WORD_FIELDS if name not in item]
            if missing:
                problems.append(f"{where}: missing {', '.join(missing)}")
                continue
            word_key = (str(item["word"]).lower(), item["pos"])
            if word_key in seen:
                problems.append(f"{where}: twice in the file ({item['pos']})")
            seen.add(word_key)
            if item["pos"] not in parts_of_speech:
                problems.append(f"{where}: unknown part of speech {item['pos']!r}")
            if not isinstance(item["band"], int) or item["band"] < 1:
                problems.append(f"{where}: band must be a whole number from 1")
            if item["level"] not in LEVELS:
                problems.append(f"{where}: level must be one of {', '.join(LEVELS)}")
            if not isinstance(item.get("forms", []), list):
                problems.append(f"{where}: forms must be a list")
            if not item["senses"]:
                problems.append(f"{where}: no meaning")
            unknown = [key for key in item["senses"] if key not in available]
            if unknown:
                problems.append(f"{where}: unknown concepts {', '.join(unknown)}")
    return problems


def layer_keys(layer):
    return {item["id"] for item in layer.concepts if isinstance(item.get("id"), str)}


def known_concept_keys():
    return set(Concept.objects.values_list("key", flat=True))


def save_tags(tag_data):
    """Create or update the tags; parents first, so children can point to them."""
    tags = {}
    for item in sorted(tag_data, key=lambda item: item["parent"] is not None):
        tag, _created = LexiconTag.objects.update_or_create(
            slug=item["slug"],
            defaults={"name": item["name"], "parent": tags.get(item["parent"])},
        )
        tags[tag.slug] = tag
    return tags


@dataclass
class Saved:
    concepts_added: int = 0
    concepts_changed: int = 0
    words_added: int = 0
    words_changed: int = 0


def save_layer(layer, tags_by_slug):
    """Put a layer into the database (concepts first, then the words). Returns Saved."""
    saved = Saved()
    concept_ids = _save_concepts(layer, tags_by_slug, saved)
    _save_words(layer, concept_ids, saved)
    return saved


def _save_concepts(layer, tags_by_slug, saved):
    keys = [item["id"] for item in layer.concepts]
    existing = dict(Concept.objects.filter(key__in=keys).values_list("key", "pk"))
    new = [Concept(key=key, source=layer.source) for key in keys if key not in existing]
    for concept in Concept.objects.bulk_create(new, batch_size=BATCH):
        existing[concept.key] = concept.pk
    saved.concepts_added += len(new)
    saved.concepts_changed += len(keys) - len(new)
    new_keys = {concept.key for concept in new}

    # Tags: given ones replace the old ones; a new concept without tags has none
    Through = Concept.tags.through
    tagged = [item for item in layer.concepts if "tags" in item]
    Through.objects.filter(
        concept_id__in=[existing[item["id"]] for item in tagged if item["id"] not in new_keys]
    ).delete()
    Through.objects.bulk_create(
        [
            Through(concept_id=existing[item["id"]], lexicontag_id=tags_by_slug[slug].pk)
            for item in tagged
            for slug in dict.fromkeys(item["tags"])
        ],
        batch_size=BATCH,
    )

    # Texts: the languages of the layer replace those languages, the others stay
    old_texts = {
        (text.concept_id, text.language): text
        for text in ConceptText.objects.filter(concept_id__in=existing.values())
    }
    create, update = [], []
    for item in layer.concepts:
        concept_id = existing[item["id"]]
        for language, text in item.get("texts", {}).items():
            values = {
                "words": text["words"].strip(),
                "note": text.get("note", "").strip(),
                "sentence": text.get("sentence", "").strip(),
            }
            row = old_texts.get((concept_id, language))
            if row is None:
                create.append(ConceptText(concept_id=concept_id, language=language, **values))
            else:
                for name, value in values.items():
                    setattr(row, name, value)
                update.append(row)
    ConceptText.objects.bulk_create(create, batch_size=BATCH)
    ConceptText.objects.bulk_update(update, ["words", "note", "sentence"], batch_size=BATCH)
    _index_texts([*create, *update])
    return existing


def _index_texts(texts):
    """The words of each text as forms, so a typed word is found in the column of its language."""
    ConceptTextForm.objects.filter(text__in=[text.pk for text in texts]).delete()
    ConceptTextForm.objects.bulk_create(
        [
            ConceptTextForm(text_id=text.pk, form=form)
            for text in texts
            for form in dict.fromkeys(
                variant.strip().lower() for variant in text.words.split(";") if variant.strip()
            )
        ],
        batch_size=BATCH,
    )


def _save_words(layer, concept_ids, saved):
    for language, words in layer.words.items():
        keys = {(item["word"].lower(), item["pos"]) for item in words}
        old = [
            word.pk
            for word in LexiconWord.objects.filter(language=language).only(
                "pk", "word", "part_of_speech"
            )
            if (word.word.lower(), word.part_of_speech) in keys
        ]
        LexiconWord.objects.filter(pk__in=old).delete()
        saved.words_changed += len(old)
        saved.words_added += len(words) - len(old)

        needed = {key for item in words for key in item["senses"]} - set(concept_ids)
        concept_ids.update(Concept.objects.filter(key__in=needed).values_list("key", "pk"))
        created = LexiconWord.objects.bulk_create(
            [
                LexiconWord(
                    language=language,
                    word=item["word"],
                    part_of_speech=item["pos"],
                    band=item["band"],
                    level=item["level"],
                    ipa=item.get("ipa", ""),
                    gender=item.get("gender", ""),
                    source=layer.source,
                )
                for item in words
            ],
            batch_size=BATCH,
        )
        forms, senses = [], []
        for word, item in zip(created, words, strict=True):
            texts = dict.fromkeys(text.lower() for text in [item["word"], *item.get("forms", [])])
            forms.extend(WordForm(word=word, text=text) for text in texts)
            for position, key in enumerate(dict.fromkeys(item["senses"])):
                senses.append(WordSense(word=word, concept_id=concept_ids[key], position=position))
        WordForm.objects.bulk_create(forms, batch_size=BATCH)
        WordSense.objects.bulk_create(senses, batch_size=BATCH)


def convert_old(items, foreign="en", native="cs"):
    """Old format (one entry per line, meanings with translation and two sentences) to the
    new one: (concept lines, word lines). Each meaning becomes the concept word.pos.number."""
    concepts, words = [], []
    for item in items:
        keys = []
        for number, sense in enumerate(item["senses"], start=1):
            key = f"{item['word']}.{item['pos']}.{number}"
            keys.append(key)
            concepts.append(
                {
                    "id": key,
                    "tags": sense.get("tags", []),
                    "texts": {
                        foreign: {"words": item["word"], "sentence": sense["sentence"]},
                        native: {
                            "words": sense["cs"],
                            "note": sense.get("note", ""),
                            "sentence": sense.get("sentence_cs", ""),
                        },
                    },
                }
            )
        words.append(
            {
                "word": item["word"],
                "pos": item["pos"],
                "band": item["band"],
                "level": item["level"],
                "ipa": item.get("ipa", ""),
                "forms": item.get("forms", []),
                "senses": keys,
            }
        )
    return concepts, words


def write_layer(folder, concepts, words_by_language):
    """Write the files of a layer (used by the conversion and the tests)."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / CONCEPTS_FILE).write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in concepts),
        encoding="utf-8",
    )
    for language, words in words_by_language.items():
        (folder / f"words_{language}.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in words),
            encoding="utf-8",
        )
