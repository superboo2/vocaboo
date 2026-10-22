"""Import the whole dictionary of the app into the database: the base and all packages.

    uv run python manage.py import_lexicon            # dictionary/data + extensions/<day>/
    uv run python manage.py import_lexicon --check    # only check the files, write nothing
    uv run python manage.py import_lexicon --data some/folder   # another base folder

Importing replaces the whole dictionary, so the files are the original and the database only
a copy (on a new server: copy dictionary/data/ and run this). The packages come after the base,
the oldest first. The files and their format: docs/slovnik.md.
"""

import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dictionary import lexicon_files
from dictionary.models import Concept, LexiconPackage, LexiconWord


class Command(BaseCommand):
    help = "Import the dictionary of the app: the base and all packages (replaces the old data)."

    def add_arguments(self, parser):
        parser.add_argument("--data", help="Base folder (default: dictionary/data)")
        parser.add_argument("--tags", help="Tags file (default: lexicon_tags.json in it)")
        parser.add_argument("--check", action="store_true", help="Only check, write nothing")

    def handle(self, data=None, tags=None, check=False, **options):
        folder = pathlib.Path(data) if data else lexicon_files.DATA_DIR
        tags_path = pathlib.Path(tags) if tags else folder / "lexicon_tags.json"
        packages = [] if data else lexicon_files.package_folders()
        try:
            tag_data = lexicon_files.read_tags(tags_path)
            layers = [lexicon_files.read_layer(folder, lexicon_files.BASE_SOURCE)]
            layers += [lexicon_files.read_layer(package, package.name) for package in packages]
        except lexicon_files.LexiconFileError as error:
            raise CommandError(str(error)) from error

        slugs = {tag["slug"] for tag in tag_data}
        known = set()
        problems = []
        for layer in layers:
            problems += lexicon_files.check(layer, slugs, known)
            known |= lexicon_files.layer_keys(layer)
        if problems:
            raise CommandError("\n".join(["Nothing imported:", *problems]))
        if check:
            words = sum(len(items) for layer in layers for items in layer.words.values())
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: {len(known)} concepts, {words} words, {len(packages)} packages."
                )
            )
            return

        with transaction.atomic():
            LexiconWord.objects.all().delete()
            Concept.objects.all().delete()
            tags_by_slug = lexicon_files.save_tags(tag_data)
            for layer in layers:
                lexicon_files.save_layer(layer, tags_by_slug)
            # Now exactly these packages are in the database (extend_lexicon --new)
            LexiconPackage.objects.all().delete()
            LexiconPackage.objects.bulk_create(LexiconPackage(name=p.name) for p in packages)
        languages = ", ".join(
            sorted(set(LexiconWord.objects.values_list("language", flat=True).distinct()))
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {Concept.objects.count()} concepts and {LexiconWord.objects.count()} "
                f"words ({languages}), {len(tags_by_slug)} tags, {len(packages)} packages."
            )
        )
