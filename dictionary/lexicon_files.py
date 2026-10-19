"""Files of the dictionary of the app: read, check and save into the database.

The dictionary is files, the database is only a copy for fast lookups (see docs/slovnik.md):

    dictionary/data/lexicon_en_cs.jsonl            the base (source "base")
    dictionary/data/lexicon_tags.json              the tags of the meanings
    dictionary/data/extensions/2026-10-19.jsonl    packages of new words (source = file name)

One line of a file is one headword (a word with one part of speech) as JSON. A later file
replaces an entry with the same word and part of speech, so a package can also change a word.
"""

import json
import pathlib
import re

from django.conf import settings

from .models import LexiconEntry, LexiconForm, LexiconSense, LexiconTag

DATA_DIR = pathlib.Path(settings.BASE_DIR) / "dictionary" / "data"
BASE_FILE = DATA_DIR / "lexicon_en_cs.jsonl"
TAGS_FILE = DATA_DIR / "lexicon_tags.json"
EXTENSIONS_DIR = DATA_DIR / "extensions"
BASE_SOURCE = "base"
# A package is named by the day it was made, e.g. 2026-10-19.jsonl (so the names sort by date)
PACKAGE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}(-\d+)?$")

FIELDS = ("word", "pos", "band", "level", "ipa", "forms", "senses")
SENSE_FIELDS = ("cs", "note", "sentence", "sentence_cs", "tags")
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
BATCH = 2000


class LexiconFileError(Exception):
    """The file cannot be imported; the message says where and why."""


def read_file(path):
    """The lines of a JSONL file as dicts."""
    path = pathlib.Path(path)
    if not path.exists():
        raise LexiconFileError(f"File not found: {path}")
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise LexiconFileError(f"{path.name}:{number}: bad JSON: {error}") from error
    return items


def read_tags(path=TAGS_FILE):
    path = pathlib.Path(path)
    if not path.exists():
        raise LexiconFileError(f"Tags file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LexiconFileError(f"{path.name}: bad JSON: {error}") from error


def package_files():
    """The packages of new words, the oldest first."""
    if not EXTENSIONS_DIR.exists():
        return []
    return sorted(path for path in EXTENSIONS_DIR.glob("*.jsonl") if PACKAGE_NAME.match(path.stem))


def check(items, tag_slugs, name):
    """All mistakes of a file as texts like "2026-10-19:3 ogre: no {word} in the sentence"."""
    problems = []
    seen = set()
    parts_of_speech = set(LexiconEntry.PartOfSpeech.values)
    for number, item in enumerate(items, start=1):
        where = f"{name}:{number} {item.get('word', '?')}"
        missing = [field for field in FIELDS if field not in item]
        if missing:
            problems.append(f"{where}: missing {', '.join(missing)}")
            continue
        key = (str(item["word"]).lower(), item["pos"])
        if key in seen:
            problems.append(f"{where}: twice in the file ({item['pos']})")
        seen.add(key)
        if item["pos"] not in parts_of_speech:
            problems.append(f"{where}: unknown part of speech {item['pos']!r}")
        if not isinstance(item["band"], int) or item["band"] < 1:
            problems.append(f"{where}: band must be a whole number from 1")
        if item["level"] not in LEVELS:
            problems.append(f"{where}: level must be one of {', '.join(LEVELS)}")
        if not isinstance(item["forms"], list):
            problems.append(f"{where}: forms must be a list")
        if not item["senses"]:
            problems.append(f"{where}: no meaning")
        for sense in item["senses"]:
            missing = [field for field in SENSE_FIELDS if field not in sense]
            if missing:
                problems.append(f"{where}: a meaning without {', '.join(missing)}")
                continue
            if not sense["cs"].strip():
                problems.append(f"{where}: a meaning without a translation")
            if not re.search(r"\{[^{}]+\}", sense["sentence"]):
                problems.append(f"{where}: no {{word}} in the sentence {sense['sentence']!r}")
            unknown = [slug for slug in sense["tags"] if slug not in tag_slugs]
            if unknown:
                problems.append(f"{where}: unknown tags {', '.join(unknown)}")
    return problems


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


def save_entries(items, tags_by_slug, source, foreign="en", native="cs"):
    """Put the entries of a file into the database; the same word + part of speech that is
    already there is replaced. Returns (added, replaced, number of meanings)."""
    existing = LexiconEntry.objects.filter(foreign_code=foreign, native_code=native)
    keys = {(item["word"].lower(), item["pos"]) for item in items}
    old = [
        entry.pk
        for entry in existing.only("pk", "word", "part_of_speech")
        if (entry.word.lower(), entry.part_of_speech) in keys
    ]
    LexiconEntry.objects.filter(pk__in=old).delete()

    entries = LexiconEntry.objects.bulk_create(
        [
            LexiconEntry(
                foreign_code=foreign,
                native_code=native,
                word=item["word"],
                part_of_speech=item["pos"],
                band=item["band"],
                level=item["level"],
                ipa=item["ipa"],
                source=source,
            )
            for item in items
        ],
        batch_size=BATCH,
    )
    forms = []
    senses = []
    sense_tags = []
    for entry, item in zip(entries, items, strict=True):
        texts = dict.fromkeys(text.lower() for text in [item["word"], *item["forms"]])
        forms.extend(LexiconForm(entry=entry, text=text) for text in texts)
        for position, sense in enumerate(item["senses"]):
            senses.append(
                LexiconSense(
                    entry=entry,
                    position=position,
                    translation=sense["cs"],
                    note=sense["note"],
                    sentence=sense["sentence"],
                    sentence_native=sense["sentence_cs"],
                )
            )
            sense_tags.append(sense["tags"])
    LexiconForm.objects.bulk_create(forms, batch_size=BATCH)
    senses = LexiconSense.objects.bulk_create(senses, batch_size=BATCH)

    Through = LexiconSense.tags.through
    links = [
        Through(lexiconsense_id=sense.pk, lexicontag_id=tags_by_slug[slug].pk)
        for sense, slugs in zip(senses, sense_tags, strict=True)
        for slug in slugs
    ]
    Through.objects.bulk_create(links, batch_size=BATCH)
    return len(items) - len(old), len(old), len(senses)
