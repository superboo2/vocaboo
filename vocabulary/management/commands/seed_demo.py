"""Fill a user account with sample decks and words, to try the app quickly.

    uv run python manage.py seed_demo martin@example.com

Existing data is never changed: when the sample decks already exist, nothing happens.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vocabulary import services
from vocabulary.models import Deck, Language

ENGLISH_ROOT = "Angličtina (ukázka)"
SPANISH_ROOT = "Španělština (ukázka)"

# (foreign, native, sentence, source, meaning hint)
HIMYM_S01 = [
    ("hello; hi", "ahoj; čau", "Kids, I'm going to tell you an incredible story.", "S01E01", ""),
    ("legendary", "legendární", "It's going to be legen... wait for it... dary!", "S01E01", ""),
    ("suit up", "obleč se do obleku", "Suit up!", "S01E01", ""),
    ("awesome", "úžasný; skvělý", "Haaave you met Ted? It's awesome.", "S01E02", ""),
    ("palm", "dlaň", "She read my palm.", "S01E03", "ruka"),
    ("bet", "sázka; sázet se", "I bet you can't do it.", "S01E04", ""),
]
BBT_S01 = [
    ("hello; hi", "ahoj; čau", "Hello, Penny.", "S01E01", ""),
    ("physics", "fyzika", "I'm a theoretical physicist.", "S01E01", ""),
    ("roommate", "spolubydlící", "He's my roommate.", "S01E01", ""),
    ("palm", "palma", "There's a palm tree on the beach.", "S01E05", "strom"),
]
SHREK = [
    ("ogre", "zlobr", "Ogres are like onions.", "", ""),
    ("onion", "cibule", "Ogres are like onions.", "", ""),
    ("swamp", "bažina", "What are you doing in my swamp?", "", ""),
]
SPANISH = [
    ("hola", "ahoj", "¡Hola, amigo!", "", ""),
    ("gracias", "děkuji; díky", "Muchas gracias.", "", ""),
    ("amigo; amiga", "přítel; kamarád", "Eres mi amigo.", "", ""),
]


class Command(BaseCommand):
    help = "Add sample decks and words to a user account (nothing is changed when they exist)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email of an existing user")

    def handle(self, email, **options):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No user with email {email}. Create one with createsuperuser.")
        if Deck.objects.filter(owner=user, parent=None, name__in=[ENGLISH_ROOT, SPANISH_ROOT]):
            self.stdout.write("Sample decks already exist, nothing was changed.")
            return

        languages = {language.code: language for language in Language.objects.all()}
        missing = {"cs", "en", "es"} - set(languages)
        if missing:
            raise CommandError(f"Missing languages: {', '.join(sorted(missing))}. Run migrate.")

        with transaction.atomic():
            count = self._create(user, languages)
        self.stdout.write(self.style.SUCCESS(f"Added sample decks with {count} words."))

    def _create(self, user, languages):
        english = services.create_deck(
            user,
            ENGLISH_ROOT,
            foreign_language=languages["en"],
            native_language=languages["cs"],
            description="Ukázková data z příkazu seed_demo. Klidně je smaž.",
        )
        series = services.create_deck(user, "Seriály", parent=english)
        himym = services.create_deck(user, "HIMYM", parent=series)
        himym_s01 = services.create_deck(user, "S01", parent=himym)
        bbt = services.create_deck(user, "Big Bang Theory", parent=series)
        films = services.create_deck(user, "Filmy", parent=english)
        shrek = services.create_deck(user, "Shrek", parent=films)
        spanish = services.create_deck(
            user,
            SPANISH_ROOT,
            foreign_language=languages["es"],
            native_language=languages["cs"],
        )

        count = 0
        for deck, words in [
            (himym_s01, HIMYM_S01),
            (bbt, BBT_S01),
            (shrek, SHREK),
            (spanish, SPANISH),
        ]:
            for foreign, native, sentence, source, hint in words:
                count += self._add(deck, foreign, native, sentence, source, hint)
        return count

    def _add(self, deck, foreign, native, sentence, source, hint):
        """Add the word, or put the existing one into this deck. Returns 1 for a new word."""
        check = services.find_duplicates(deck, foreign=foreign, native=native, meaning_hint=hint)
        if check.exact is not None:
            services.link_term(
                deck,
                check.exact.term,
                foreign=foreign,
                native=native,
                context_sentence=sentence,
                context_source=source,
            )
            return 0
        # A new meaning of a word without a hint gives the old word a hint too
        existing_hints = {term.pk: "jiný význam" for term in check.need_hint}
        services.add_term(
            deck,
            foreign=foreign,
            native=native,
            context_sentence=sentence,
            context_source=source,
            meaning_hint=hint,
            existing_hints=existing_hints,
        )
        return 1
