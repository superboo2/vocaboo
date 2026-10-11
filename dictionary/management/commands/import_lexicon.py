"""Import the dictionary of the app (own English–Czech data) into the database.

    uv run python manage.py import_lexicon dictionary/data/lexicon_en_cs.jsonl

The file has one headword (word + part of speech) per line as JSON; the tags are in
lexicon_tags.json next to it (or --tags). Importing again replaces all entries of the same
language pair, so the file is the original and the database only a copy for fast lookups.
"""

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary.models import LexiconEntry, LexiconForm, LexiconSense, LexiconTag

BATCH = 2000


class Command(BaseCommand):
    help = "Import the dictionary of the app from a JSONL file (replaces the old data)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSONL file, e.g. dictionary/data/lexicon_en_cs.jsonl")
        parser.add_argument("--tags", help="Tags file (default: lexicon_tags.json next to it)")
        parser.add_argument("--foreign", default="en", help="Language of the words (default en)")
        parser.add_argument("--native", default="cs", help="Language of the meanings (default cs)")

    def handle(self, path, tags=None, foreign="en", native="cs", **options):
        path = pathlib.Path(path)
        tags_path = pathlib.Path(tags) if tags else path.with_name("lexicon_tags.json")
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if not tags_path.exists():
            raise CommandError(f"Tags file not found: {tags_path}")

        lines = path.read_text(encoding="utf-8").splitlines()
        try:
            data = [json.loads(line) for line in lines if line.strip()]
            tag_data = json.loads(tags_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CommandError(f"Bad JSON: {error}") from error

        with transaction.atomic():
            LexiconEntry.objects.filter(foreign_code=foreign, native_code=native).delete()
            tags_by_slug = self.import_tags(tag_data)
            senses_count = self.import_entries(data, tags_by_slug, foreign, native)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(data)} entries with {senses_count} senses "
                f"({foreign} → {native}), {len(tags_by_slug)} tags."
            )
        )

    def import_tags(self, tag_data):
        """Create or update the tags; parents first, so children can point to them."""
        tags = {}
        for item in sorted(tag_data, key=lambda item: item["parent"] is not None):
            tag, _created = LexiconTag.objects.update_or_create(
                slug=item["slug"],
                defaults={"name": item["name"], "parent": tags.get(item["parent"])},
            )
            tags[tag.slug] = tag
        return tags

    def import_entries(self, data, tags_by_slug, foreign, native):
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
                )
                for item in data
            ],
            batch_size=BATCH,
        )
        forms = []
        senses = []
        sense_tags = []
        for entry, item in zip(entries, data, strict=True):
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
        links = []
        for sense, slugs in zip(senses, sense_tags, strict=True):
            for slug in slugs:
                if slug not in tags_by_slug:
                    raise CommandError(f"Unknown tag {slug!r} at {sense.entry.word}")
                links.append(Through(lexiconsense_id=sense.pk, lexicontag_id=tags_by_slug[slug].pk))
        Through.objects.bulk_create(links, batch_size=BATCH)
        return len(senses)
