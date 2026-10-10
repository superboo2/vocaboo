"""Import the Czech Wiktionary (extracted by kaikki.org) for translation suggestions.

    curl -fLO https://kaikki.org/dictionary/downloads/cs/cs-extract.jsonl.gz
    uv run python manage.py import_wiktionary cs-extract.jsonl.gz

The Czech Wiktionary has words of many languages with their meanings written in Czech, so
every imported entry is "foreign word → Czech meanings". The file is read line by line,
so a big file does not need much memory. Importing again replaces the old data.
"""

import gzip
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary.models import DictionaryEntry

SOURCE = "cswiktionary"
NATIVE_CODE = "cs"
BATCH = 2000


def open_file(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def entry_from_line(data):
    """DictionaryEntry for one JSON line, or None when the line is not useful."""
    code = data.get("lang_code") or ""
    word = (data.get("word") or "").strip()
    if len(code) != 2 or code == NATIVE_CODE or not word or len(word) > 200:
        return None
    senses = []
    for sense in data.get("senses", []):
        glosses = [gloss.strip() for gloss in sense.get("glosses", []) if gloss.strip()]
        if not glosses:
            continue
        # Example sentences with their Czech translation when the source has one
        examples = [
            {
                "text": example["text"].strip(),
                "translation": (example.get("translation") or "").strip(),
            }
            for example in sense.get("examples", [])
            if (example.get("text") or "").strip()
        ]
        # The last gloss is the most specific one
        senses.append({"text": glosses[-1], "examples": examples[:3]})
    if not senses:
        return None
    sounds = data.get("sounds", [])
    ipa = next((sound["ipa"] for sound in sounds if sound.get("ipa")), "")
    audio = next((sound["mp3_url"] for sound in sounds if sound.get("mp3_url")), "")
    return DictionaryEntry(
        source=SOURCE,
        foreign_code=code,
        native_code=NATIVE_CODE,
        word=word,
        part_of_speech=(data.get("pos_title") or data.get("pos") or "")[:50],
        senses=senses,
        ipa=ipa[:200],
        audio_url=audio[:500],
    )


class Command(BaseCommand):
    help = "Import the Czech Wiktionary from kaikki.org (cs-extract.jsonl or .jsonl.gz)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="cs-extract.jsonl.gz downloaded from kaikki.org")
        parser.add_argument(
            "--languages",
            default="",
            help="Only these word languages, e.g. en,es (default: all)",
        )

    def handle(self, path, languages, **options):
        wanted = {code.strip() for code in languages.split(",") if code.strip()}
        try:
            source = open_file(path)
        except OSError as error:
            raise CommandError(f"Cannot open {path}: {error}") from error

        counts = {}
        with source, transaction.atomic():
            DictionaryEntry.objects.filter(source=SOURCE).delete()
            batch = []
            for number, line in enumerate(source, start=1):
                try:
                    entry = entry_from_line(json.loads(line))
                except json.JSONDecodeError as error:
                    raise CommandError(f"Line {number} is not valid JSON: {error}") from error
                if entry is None or (wanted and entry.foreign_code not in wanted):
                    continue
                batch.append(entry)
                counts[entry.foreign_code] = counts.get(entry.foreign_code, 0) + 1
                if len(batch) >= BATCH:
                    DictionaryEntry.objects.bulk_create(batch)
                    batch = []
            DictionaryEntry.objects.bulk_create(batch)

        total = sum(counts.values())
        biggest = ", ".join(
            f"{code} {count}" for code, count in sorted(counts.items(), key=lambda x: -x[1])[:8]
        )
        self.stdout.write(self.style.SUCCESS(f"Imported {total} entries ({biggest})."))
