"""The next concepts to translate into a new language of the dictionary of the app: the most
common ones (by the band of their English word) that have no text in that language yet, neither
in the base nor in any package. For the next package of the translation (docs/slovnik.md).
Only reads the files.

    uv run python manage.py translation_batch uk
    uv run python manage.py translation_batch uk --count 500 --output uk-next.jsonl

Each line is one concept with what the translation needs: its English words and sentence and
its Czech words and note, e.g.
    {"id": "cat.noun.1", "en": {"words": "cat", "sentence": "The {cat} is asleep."},
     "cs": {"words": "kočka; kocour", "note": ""}}
"""

import json

from django.core.management.base import BaseCommand, CommandError

from dictionary import lexicon_files

# What the translator gets from these languages
SOURCE = {"en": ("words", "sentence"), "cs": ("words", "note")}


class Command(BaseCommand):
    help = "List the next concepts without a text in a language, the most common first."

    def add_arguments(self, parser):
        parser.add_argument("language", help="ISO 639-1 code of the language, e.g. uk")
        parser.add_argument("--count", type=int, default=1000, help="How many (default 1000)")
        parser.add_argument("--output", help="Write the lines to this file instead of the screen.")

    def handle(self, language, count=1000, output=None, **options):
        if not lexicon_files.LANGUAGE.match(language):
            raise CommandError(f"Give a two-letter language code, not {language!r}")
        try:
            layers = [lexicon_files.read_layer(lexicon_files.DATA_DIR, lexicon_files.BASE_SOURCE)]
            layers += [
                lexicon_files.read_layer(package, package.name)
                for package in lexicon_files.package_folders()
            ]
        except lexicon_files.LexiconFileError as error:
            raise CommandError(str(error)) from error
        batch = next_batch(layers, language, count)
        lines = [json.dumps(item, ensure_ascii=False) for item in batch]
        if output:
            with open(output, "w", encoding="utf-8") as file:
                file.write("".join(f"{line}\n" for line in lines))
            self.stderr.write(f"{len(lines)} concepts written to {output}.")
        else:
            self.stdout.write("\n".join(lines))


def next_batch(layers, language, count):
    """The first `count` concepts without a text in `language`, in the order of the English
    words (band, then the order of the files) and of their meanings."""
    texts = {}
    for layer in layers:
        for item in layer.concepts:
            # A later layer replaces the texts of its languages, the others stay
            texts.setdefault(item["id"], {}).update(item.get("texts", {}))
    words = {}
    for layer in layers:
        for word in layer.words.get(lexicon_files.DEFINING_LANGUAGE, []):
            # The same word and part of speech in a later layer replaces the old one
            words[(word["word"].lower(), word["pos"])] = word
    # sorted() keeps the order of the files within one band
    ordered = sorted(words.values(), key=lambda word: word["band"])
    batch = []
    seen = set()
    for word in ordered:
        for key in word["senses"]:
            if key in seen or language in texts.get(key, {}):
                continue
            seen.add(key)
            batch.append(_item(key, texts.get(key, {})))
            if len(batch) == count:
                return batch
    return batch


def _item(key, texts):
    item = {"id": key}
    for language, fields in SOURCE.items():
        text = texts.get(language, {})
        item[language] = {name: text.get(name, "") for name in fields}
    return item
