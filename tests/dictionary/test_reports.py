"""Reported mistakes: "Report a mistake" on the word page and the command reported_words."""

import io

import pytest
from django.core.management import call_command
from django.urls import reverse

from dictionary.models import ErrorReport
from tests.conftest import lexicon_entry
from vocabulary import services

PALM = lexicon_entry(
    "palm",
    "noun",
    [
        ("dlaň", "She read my {palm}.", "Četla mi z {dlaně}."),
        ("palma", "A {palm} on the beach.", "{Palma} na pláži."),
    ],
    forms=["palms"],
)


@pytest.fixture
def deck(user, en, cs):
    return services.create_deck(user, "Seriály", foreign_language=en, native_language=cs)


@pytest.fixture
def palm(deck):
    return services.add_term(
        deck, foreign="palm", native="dlaň; ruka", context_sentence="Show me your {palm}."
    )


def report_url(deck_term):
    return reverse("vocabulary:term_report", args=[deck_term.deck_id, deck_term.pk])


def detail_url(deck_term):
    return reverse("vocabulary:term_detail", args=[deck_term.deck_id, deck_term.pk])


def test_word_page_offers_reporting_a_mistake(client, user, palm):
    client.force_login(user)

    html = client.get(detail_url(palm)).content.decode()

    assert report_url(palm) in html and "Nahlásit chybu" in html


def test_report_keeps_a_copy_of_the_word(client, user, palm):
    client.force_login(user)

    response = client.post(report_url(palm), {"kind": "translation", "note": " spíš dlaň "})

    assert response.url == detail_url(palm)
    report = ErrorReport.objects.get()
    assert (report.user, report.term, report.kind, report.note) == (
        user,
        palm.term,
        "translation",
        "spíš dlaň",
    )
    assert (report.foreign_language, report.native_language) == ("en", "cs")
    assert (report.foreign, report.native) == ("palm", "dlaň; ruka")
    assert report.sentence == "Show me your {palm}."
    # The word stays as it was
    palm.term.refresh_from_db()
    assert palm.term.native_variants == ["dlaň", "ruka"]


def test_reporting_again_changes_the_open_report(client, user, palm):
    client.force_login(user)
    client.post(report_url(palm), {"kind": "translation"})

    # The menu and the form know the open report
    assert "Upravit hlášení" in client.get(detail_url(palm)).content.decode()
    assert (
        'value="translation" required id="id_kind_0" checked'
        in client.get(report_url(palm)).content.decode()
    )

    client.post(report_url(palm), {"kind": "sentence", "note": "Věta je divná."})

    report = ErrorReport.objects.get()
    assert (report.kind, report.note) == ("sentence", "Věta je divná.")


def test_a_resolved_report_does_not_stop_a_new_one(client, user, palm):
    client.force_login(user)
    client.post(report_url(palm), {"kind": "translation"})
    ErrorReport.objects.update(resolved=True)

    assert "Nahlásit chybu" in client.get(detail_url(palm)).content.decode()
    client.post(report_url(palm), {"kind": "other"})

    assert ErrorReport.objects.count() == 2


def test_report_needs_what_is_wrong(client, user, palm):
    client.force_login(user)

    response = client.post(report_url(palm), {"note": "?"})

    assert response.status_code == 200
    assert not ErrorReport.objects.exists()


def test_report_stays_when_the_word_is_deleted(client, user, palm):
    client.force_login(user)
    client.post(report_url(palm), {"kind": "translation"})

    palm.term.delete()

    report = ErrorReport.objects.get()
    assert report.term is None and report.foreign == "palm"


def test_other_users_cannot_report_my_word(client, other_user, palm):
    client.force_login(other_user)

    assert client.get(report_url(palm)).status_code == 404
    assert client.post(report_url(palm), {"kind": "translation"}).status_code == 404
    assert not ErrorReport.objects.exists()


def test_command_lists_open_reports_with_their_concepts(lexicon, client, user, deck, palm):
    lexicon(PALM)
    palms = services.add_term(deck, foreign="palms", native="kokos")
    client.force_login(user)
    client.post(report_url(palm), {"kind": "translation", "note": "spíš dlaň"})
    client.post(report_url(palms), {"kind": "other"})
    # A resolved one is not listed
    hello = services.add_term(deck, foreign="hello", native="ahoj")
    client.post(report_url(hello), {"kind": "other"})
    ErrorReport.objects.filter(foreign="hello").update(resolved=True)

    out = io.StringIO()
    call_command("reported_words", stdout=out)

    text = out.getvalue()
    # The translation "dlaň" picks the meaning; with an unknown translation all meanings
    assert "palm → dlaň; ruka" in text and "note: spíš dlaň" in text
    assert "concepts: palm.noun.1\n" in text
    assert "concepts: palm.noun.1, palm.noun.2" in text
    assert "hello" not in text


def test_command_says_when_nothing_is_open(db):
    out = io.StringIO()
    call_command("reported_words", stdout=out)

    assert out.getvalue().strip() == "No open reports."


def test_report_page_names_the_parts_of_the_word(client, user, palm):
    client.force_login(user)

    html = client.get(report_url(palm)).content.decode()

    # The choices "návrh překladu / věty" point at the rows with these labels
    assert "<dt>Překlad:</dt>" in html and "dlaň · ruka" in html
    assert "<dt>Věta:</dt>" in html
    # No translation of the sentence, no row for it
    assert "Překlad věty:" not in html
