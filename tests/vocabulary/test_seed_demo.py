import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from vocabulary.models import Deck, DeckTerm, Term


def test_seed_demo_adds_sample_data(user, capsys):
    call_command("seed_demo", "Martin@Example.com")

    assert Deck.objects.filter(owner=user, parent=None).count() == 2
    assert Term.objects.filter(owner=user, main_foreign="palm").count() == 2
    # "hello" is in HIMYM and in Big Bang Theory, but it is one word
    hello = Term.objects.get(owner=user, main_foreign="hello")
    assert DeckTerm.objects.filter(term=hello).count() == 2
    assert "Added sample decks" in capsys.readouterr().out


def test_seed_demo_twice_changes_nothing(user, capsys):
    call_command("seed_demo", user.email)
    words = Term.objects.count()

    call_command("seed_demo", user.email)

    assert Term.objects.count() == words
    assert "nothing was changed" in capsys.readouterr().out


def test_seed_demo_needs_existing_user(db):
    with pytest.raises(CommandError):
        call_command("seed_demo", "nobody@example.com")
