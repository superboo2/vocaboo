"""Add a package of new words to the dictionary of the app (the rest stays as it is).

    uv run python manage.py extend_lexicon dictionary/data/extensions/2026-11-02
    uv run python manage.py extend_lexicon dictionary/data/extensions/2026-11-02 --check
    uv run python manage.py extend_lexicon --new    # every package not added yet, oldest first

A package is a folder named by its day with concepts.jsonl, words_<language>.jsonl and
report.txt (what was done with the words of missing_words: changed, fixed, skipped), which is
printed. Everything is checked first; with a mistake nothing is written. A known concept gets
the texts of the languages in the package, a word with the same language, word and part of
speech is replaced, so running the same package again changes nothing. Keep the package in
dictionary/data/extensions/: a full import_lexicon (new server) reads it again. The database
remembers the added packages (LexiconPackage), so --new adds only the others; deploy/deploy.sh
runs it after every update.
See docs/slovnik.md.
"""

import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary import lexicon_files
from dictionary.models import LexiconPackage


class Command(BaseCommand):
    help = "Add a package of new words (a folder) to the dictionary of the app."

    def add_arguments(self, parser):
        parser.add_argument(
            "path", nargs="?", help="The package, e.g. dictionary/data/extensions/2026-11-02"
        )
        parser.add_argument(
            "--new", action="store_true", help="Add every package that is not added yet"
        )
        parser.add_argument("--tags", help="Tags file (default: dictionary/data/lexicon_tags.json)")
        parser.add_argument("--check", action="store_true", help="Only check, write nothing")

    def handle(self, path=None, tags=None, check=False, new=False, **options):
        if new:
            self.add_new_packages(tags, check)
            return
        if not path:
            raise CommandError("Give the package folder, or --new for all packages not added yet")
        self.add_package(pathlib.Path(path), tags, check)

    def add_new_packages(self, tags, check):
        added = set(LexiconPackage.objects.values_list("name", flat=True))
        folders = [path for path in lexicon_files.package_folders() if path.name not in added]
        if not folders:
            self.stdout.write("No new packages of the dictionary.")
            return
        for path in folders:
            self.add_package(path, tags, check)

    def add_package(self, path, tags, check):
        if not lexicon_files.PACKAGE_NAME.match(path.name):
            raise CommandError(f"Name the package by its day (2026-11-02), not {path.name}")
        try:
            tag_data = lexicon_files.read_tags(tags or lexicon_files.TAGS_FILE)
            layer = lexicon_files.read_layer(path, path.name)
        except lexicon_files.LexiconFileError as error:
            raise CommandError(str(error)) from error
        slugs = {tag["slug"] for tag in tag_data}
        problems = lexicon_files.check(layer, slugs, lexicon_files.known_concept_keys())
        if problems:
            raise CommandError("\n".join(["Nothing written:", *problems]))

        report = path / lexicon_files.REPORT_FILE
        if report.exists():
            self.stdout.write(report.read_text(encoding="utf-8").rstrip())
        if check:
            words = sum(len(items) for items in layer.words.values())
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: {len(layer.concepts)} concepts, {words} words in {path.name}."
                )
            )
            return

        with transaction.atomic():
            tags_by_slug = lexicon_files.save_tags(tag_data)
            saved = lexicon_files.save_layer(layer, tags_by_slug)
            LexiconPackage.objects.update_or_create(name=path.name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Package {path.name}: concepts added {saved.concepts_added}, changed "
                f"{saved.concepts_changed}; words added {saved.words_added}, changed "
                f"{saved.words_changed}."
            )
        )
