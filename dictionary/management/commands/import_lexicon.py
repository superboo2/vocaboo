"""Import the whole dictionary of the app into the database: the base and all packages.

    uv run python manage.py import_lexicon            # base + dictionary/data/extensions/*.jsonl
    uv run python manage.py import_lexicon --check    # only check the files, write nothing
    uv run python manage.py import_lexicon some.jsonl # only this file (tags next to it)

Importing replaces all entries of the language pair, so the files are the original and the
database only a copy (on a new server: copy dictionary/data/ and run this). A package adds
words or replaces the same word + part of speech of the files before it. See docs/slovnik.md.
"""

import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary import lexicon_files
from dictionary.models import LexiconEntry


class Command(BaseCommand):
    help = "Import the dictionary of the app: the base and all packages (replaces the old data)."

    def add_arguments(self, parser):
        parser.add_argument(
            "path", nargs="?", help="Only this JSONL file (default: the base and all packages)"
        )
        parser.add_argument("--tags", help="Tags file (default: lexicon_tags.json next to it)")
        parser.add_argument("--foreign", default="en", help="Language of the words (default en)")
        parser.add_argument("--native", default="cs", help="Language of the meanings (default cs)")
        parser.add_argument("--check", action="store_true", help="Only check, write nothing")

    def handle(self, path=None, tags=None, foreign="en", native="cs", check=False, **options):
        if path:
            path = pathlib.Path(path)
            files = [(path, lexicon_files.BASE_SOURCE)]
            tags_path = pathlib.Path(tags) if tags else path.with_name("lexicon_tags.json")
        else:
            files = [(lexicon_files.BASE_FILE, lexicon_files.BASE_SOURCE)]
            files += [(package, package.stem) for package in lexicon_files.package_files()]
            tags_path = pathlib.Path(tags) if tags else lexicon_files.TAGS_FILE

        try:
            tag_data = lexicon_files.read_tags(tags_path)
            loaded = [(lexicon_files.read_file(file), source, file) for file, source in files]
        except lexicon_files.LexiconFileError as error:
            raise CommandError(str(error)) from error
        slugs = {tag["slug"] for tag in tag_data}
        problems = [
            problem
            for items, _source, file in loaded
            for problem in lexicon_files.check(items, slugs, file.stem)
        ]
        if problems:
            raise CommandError("\n".join(["Nothing imported:", *problems]))
        if check:
            count = sum(len(items) for items, _source, _file in loaded)
            self.stdout.write(self.style.SUCCESS(f"OK: {len(loaded)} files, {count} entries."))
            return

        senses = 0
        with transaction.atomic():
            LexiconEntry.objects.filter(foreign_code=foreign, native_code=native).delete()
            tags_by_slug = lexicon_files.save_tags(tag_data)
            for items, source, _file in loaded:
                senses += lexicon_files.save_entries(items, tags_by_slug, source, foreign, native)[
                    2
                ]
        entries = LexiconEntry.objects.filter(foreign_code=foreign, native_code=native).count()
        packages = len(loaded) - 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {entries} entries with {senses} senses ({foreign} → {native}), "
                f"{len(tags_by_slug)} tags, {packages} packages."
            )
        )
