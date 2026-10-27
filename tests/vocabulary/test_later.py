"""Words for later: saved without a translation, translated and added to the deck later."""

import pytest
from django.urls import reverse

from dictionary.management.commands.missing_words import find_missing_words
from study.models import ReviewState
from vocabulary import services
from vocabulary.models import DeckTerm, PendingWord

HTMX = {"HX-Request": "true"}


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def himym(user, en, cs):
    english = services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    return services.create_deck(user, "HIMYM", parent=english)


def test_deck_form_saves_a_word_for_later(logged_client, himym):
    response = logged_client.post(
        reverse("vocabulary:term_later", args=[himym.pk]),
        {
            "foreign": "gnarly",
            "native": "",
            "context_sentence": "That was gnarly.",
            "note": "S02E05",
        },
        headers=HTMX,
    )

    pending = PendingWord.objects.get()
    assert (pending.foreign, pending.deck, pending.context_sentence, pending.note) == (
        "gnarly",
        himym,
        "That was gnarly.",
        "S02E05",
    )
    html = response.content.decode()
    assert '<span class="later-icon" aria-hidden="true">📝</span> Odloženo: gnarly' in html
    # The count is in the card under the form (refreshed with the answer)
    assert "1 slovíčko čeká na překlad" in html
    # Not a word of the deck: no tests, no counts
    assert not DeckTerm.objects.exists()
    assert not ReviewState.objects.exists()


def test_suggestions_offer_saving_a_word_they_do_not_know(logged_client, himym):
    url = reverse("vocabulary:term_suggest", args=[himym.pk])

    unknown = logged_client.get(url, {"foreign": "gnarly"}, headers=HTMX).content.decode()
    empty = logged_client.get(url, {"foreign": ""}, headers=HTMX).content.decode()

    assert "Nápověda slovo nezná" in unknown and "Odložit" in unknown
    assert "Nápověda slovo nezná" not in empty


def test_deck_form_saves_for_later_only_from_the_suggestions(logged_client, himym):
    html = logged_client.get(reverse("vocabulary:deck_detail", args=[himym.pk])).content.decode()

    # No link under "Add word": the row of suggestions offers it when it does not know the word
    assert "Odložit</span>" not in html


def test_word_for_later_needs_the_foreign_word(logged_client, himym):
    response = logged_client.post(
        reverse("vocabulary:term_later", args=[himym.pk]), {"foreign": " "}, headers=HTMX
    )

    assert "Napiš slovíčko." in response.content.decode()
    assert not PendingWord.objects.exists()


def test_list_is_a_table_with_a_way_back(logged_client, himym):
    services.save_for_later(himym, foreign="gnarly", note="S02E05")

    one_deck = logged_client.get(reverse("vocabulary:later_list") + f"?deck={himym.pk}")
    all_decks = logged_client.get(reverse("vocabulary:later_list"))

    html = one_deck.content.decode()
    assert '<table class="later-table">' in html
    assert "Zpět do slovníku HIMYM" in html
    # Of all decks: the deck column, and the way back to the overview
    html = all_decks.content.decode()
    assert "HIMYM" in html
    assert reverse("dashboard") in html


def test_no_quick_save_in_the_bar(logged_client, himym):
    html = logged_client.get(reverse("dashboard")).content.decode()

    assert "later-link" not in html


def test_list_opens_the_usual_form_of_the_deck_filled_in(logged_client, himym):
    pending = services.save_for_later(
        himym, foreign="gnarly", context_sentence="That was {gnarly}.", note="S02E05"
    )
    list_html = logged_client.get(reverse("vocabulary:later_list")).content.decode()
    link = reverse("vocabulary:deck_detail", args=[himym.pk]) + f"?later={pending.pk}"
    assert link in list_html

    html = logged_client.get(link).content.decode()

    # The usual form: the foreign word, the sentence and the note filled in, the cursor in
    # the translation, the word for later remembered in a hidden field
    assert 'value="gnarly"' in html
    assert "That was {gnarly}." in html and "S02E05" in html
    assert f'name="later" value="{pending.pk}"' in html
    assert 'name="native"' in html and "autofocus" in html
    # app.js shows the section with its heading when needed; the foreign word lights up
    assert 'id="new-word"' in html
    assert 'class="just-filled"' in html


def test_adding_from_the_form_removes_the_word_for_later(logged_client, himym):
    pending = services.save_for_later(himym, foreign="gnarly", note="S02E05")
    services.save_for_later(himym, foreign="schmooze")

    response = logged_client.post(
        reverse("vocabulary:term_add", args=[himym.pk]),
        {
            "foreign": "gnarly",
            "native": "drsný; hustý",
            "context_sentence": "That was {gnarly}.",
            "note": "S02E05",
            "later": pending.pk,
        },
        headers=HTMX,
    )

    deck_term = DeckTerm.objects.get()
    assert deck_term.term.main_native == "drsný"
    assert deck_term.term.note == "S02E05"
    assert ReviewState.objects.filter(term=deck_term.term).count() == 2
    assert list(PendingWord.objects.values_list("foreign", flat=True)) == ["schmooze"]
    # Back to the next word for later
    assert "Další odložené (1)" in response.content.decode()


def test_a_failed_add_keeps_the_word_for_later(logged_client, himym):
    pending = services.save_for_later(himym, foreign="gnarly")

    response = logged_client.post(
        reverse("vocabulary:term_add", args=[himym.pk]),
        {"foreign": "gnarly", "native": "", "later": pending.pk},
        headers=HTMX,
    )

    assert PendingWord.objects.exists()
    assert not DeckTerm.objects.exists()
    # The form still knows it, the next try removes it
    assert f'name="later" value="{pending.pk}"' in response.content.decode()


def test_list_shows_words_and_removes_them(logged_client, himym):
    pending = services.save_for_later(himym, foreign="gnarly")

    html = logged_client.get(reverse("vocabulary:later_list")).content.decode()
    assert "gnarly" in html and "HIMYM" in html

    logged_client.post(reverse("vocabulary:later_delete", args=[pending.pk]))
    assert not PendingWord.objects.exists()


def test_other_users_cannot_touch_my_words_for_later(client, other_user, himym):
    pending = services.save_for_later(himym, foreign="gnarly")
    client.force_login(other_user)

    assert "gnarly" not in client.get(reverse("vocabulary:later_list")).content.decode()
    assert client.post(reverse("vocabulary:later_delete", args=[pending.pk])).status_code == 404
    # Another user's word for later does not fill the form of my deck either
    assert PendingWord.objects.filter(pk=pending.pk).exists()


def test_overview_and_deck_remind_of_words_for_later(logged_client, himym):
    services.save_for_later(himym, foreign="gnarly")

    overview = logged_client.get(reverse("dashboard")).content.decode()
    deck_page = logged_client.get(
        reverse("vocabulary:deck_detail", args=[himym.pk])
    ).content.decode()

    assert "1 slovíčko čeká na překlad" in overview and "Doplnit" in overview
    assert "Odložené" in overview and "📝" not in overview
    # On the deck page the card is under the form and the word fills the form at once (HTMX)
    pending = PendingWord.objects.get()
    assert f"later/?deck={himym.pk}" in deck_page
    assert reverse("vocabulary:term_from_later", args=[himym.pk, pending.pk]) in deck_page


def test_missing_words_lists_words_for_later(himym):
    services.save_for_later(himym, foreign="Gnarly")

    assert "gnarly" in find_missing_words()


def test_overview_card_shows_only_the_first_two_words(logged_client, himym):
    for word in ["gnarly", "schmooze", "bummer"]:
        services.save_for_later(himym, foreign=word)

    html = logged_client.get(reverse("dashboard")).content.decode()

    # The newest two, then "…"
    assert "bummer, schmooze, …" in html
    assert "gnarly" not in html


def test_card_word_fills_the_form_without_loading_the_page(logged_client, himym):
    pending = services.save_for_later(himym, foreign="gnarly", note="S02E05")
    url = reverse("vocabulary:term_from_later", args=[himym.pk, pending.pk])

    html = logged_client.get(url, headers=HTMX).content.decode()
    plain = logged_client.get(url)

    assert 'value="gnarly"' in html and "S02E05" in html
    assert f'name="later" value="{pending.pk}"' in html
    assert 'class="just-filled"' in html
    # The card comes along (out of band), so it stays right after adding
    assert 'id="pending-card" hx-swap-oob="true"' in html
    # Without HTMX: the deck page filled the usual way
    assert plain.url.endswith(f"?later={pending.pk}")


def test_card_is_refreshed_after_adding_the_word(logged_client, himym):
    pending = services.save_for_later(himym, foreign="gnarly")

    html = logged_client.post(
        reverse("vocabulary:term_add", args=[himym.pk]),
        {"foreign": "gnarly", "native": "drsný", "later": pending.pk},
        headers=HTMX,
    ).content.decode()

    # The box is there, empty: nothing waits any more
    assert 'id="pending-card" hx-swap-oob="true"' in html
    assert "čeká na překlad" not in html


def test_other_users_cannot_fill_the_form_with_my_word(client, other_user, himym):
    pending = services.save_for_later(himym, foreign="gnarly")
    client.force_login(other_user)
    url = reverse("vocabulary:term_from_later", args=[himym.pk, pending.pk])

    assert client.get(url, headers=HTMX).status_code == 404
