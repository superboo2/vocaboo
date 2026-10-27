"""English words the users added for which the app had no hint, because its dictionary does
not know them. For the next round of the dictionary (the AI checks them and writes new
entries). Only reads.

    uv run python manage.py missing_words
    uv run python manage.py missing_words --output missing.txt
"""

from django.core.management.base import BaseCommand

from dictionary.models import WordForm
from vocabulary.models import PendingWord, TermVariant

# The dictionary has hints for English words only
LANGUAGE = "en"


class Command(BaseCommand):
    help = "List the English words of all decks that are not in the dictionary of the app."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Write the list to this file instead of the screen.")

    def handle(self, *args, **options):
        words = find_missing_words()
        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as file:
                file.write("".join(f"{word}\n" for word in words))
        else:
            self.stdout.write("\n".join(words))


def find_missing_words():
    """English foreign words of all users (each once, A–Z) that are no form of an entry: of
    their words and of the words saved for later without a translation."""
    known = set(WordForm.objects.filter(word__language=LANGUAGE).values_list("text", flat=True))
    texts = list(
        TermVariant.objects.filter(
            side=TermVariant.Side.FOREIGN, term__foreign_language__code=LANGUAGE
        ).values_list("text", flat=True)
    )
    texts += PendingWord.objects.filter(deck__foreign_language__code=LANGUAGE).values_list(
        "foreign", flat=True
    )
    words = {text.strip().lower() for text in texts}
    return sorted(word for word in words if word not in known and _worth_listing(word))


def _worth_listing(word):
    # One letter or a number is no word for the dictionary
    return len(word) > 1 and not any(character.isdigit() for character in word)
