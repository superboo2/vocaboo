"""Add a package of new words to the dictionary of the app (the rest stays as it is).

    uv run python manage.py extend_lexicon dictionary/data/extensions/2026-10-19.jsonl
    uv run python manage.py extend_lexicon dictionary/data/extensions/2026-10-19.jsonl --check

The file is checked first; with a mistake nothing is written. Next to the package can be its
report (2026-10-19.report.txt, written with the package): which words were changed to their
basic form, fixed or skipped; it is printed. An entry with the same word and part of speech as
one in the database is replaced (e.g. a new form or meaning), so running the same package again
changes nothing. Keep the package in
dictionary/data/extensions/: a full import_lexicon (new server) reads it again. See
docs/slovnik.md.
"""

import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary import lexicon_files


class Command(BaseCommand):
    help = "Add a package of new words (JSONL) to the dictionary of the app."

    def add_arguments(self, parser):
        parser.add_argument(
            "path", help="The package, e.g. dictionary/data/extensions/2026-10-19.jsonl"
        )
        parser.add_argument("--tags", help="Tags file (default: dictionary/data/lexicon_tags.json)")
        parser.add_argument("--check", action="store_true", help="Only check, write nothing")

    def handle(self, path, tags=None, check=False, **options):
        path = pathlib.Path(path)
        if not lexicon_files.PACKAGE_NAME.match(path.stem):
            raise CommandError(
                f"Name the package by its day, e.g. 2026-10-19.jsonl, not {path.name}"
            )
        try:
            tag_data = lexicon_files.read_tags(tags or lexicon_files.TAGS_FILE)
            items = lexicon_files.read_file(path)
        except lexicon_files.LexiconFileError as error:
            raise CommandError(str(error)) from error
        problems = lexicon_files.check(items, {tag["slug"] for tag in tag_data}, path.stem)
        if problems:
            raise CommandError("\n".join(["Nothing written:", *problems]))
        # What was done with the words of missing_words (changed, fixed, skipped)
        report = path.with_suffix(".report.txt")
        if report.exists():
            self.stdout.write(report.read_text(encoding="utf-8").rstrip())
        if check:
            self.stdout.write(self.style.SUCCESS(f"OK: {len(items)} entries in {path.name}."))
            return

        with transaction.atomic():
            tags_by_slug = lexicon_files.save_tags(tag_data)
            added, replaced, senses = lexicon_files.save_entries(items, tags_by_slug, path.stem)
        self.stdout.write(
            self.style.SUCCESS(
                f"Package {path.stem}: added {added} entries, changed {replaced}, {senses} senses."
            )
        )
