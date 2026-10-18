"""The translations of the app are complete and compiled."""

import json
from pathlib import Path

import polib
import pytest
from django.conf import settings

LOCALE = Path(settings.BASE_DIR) / "locale"
# English is the language of the source texts, so it needs no catalog
TRANSLATED = [code for code, _name in settings.LANGUAGES if code != "en"]
# Texts of Python and templates, and texts of the JavaScript files
DOMAINS = ["django", "djangojs"]


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("code", TRANSLATED)
def test_every_text_is_translated(code, domain):
    po = polib.pofile(LOCALE / code / "LC_MESSAGES" / f"{domain}.po")

    assert po.untranslated_entries() == []
    assert po.fuzzy_entries() == []


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("code", TRANSLATED)
def test_compiled_catalog_is_up_to_date(code, domain):
    # After editing a .po file run: uv run python manage.py compilemessages
    folder = LOCALE / code / "LC_MESSAGES"
    po = polib.pofile(folder / f"{domain}.po")
    mo = polib.mofile(folder / f"{domain}.mo")

    def texts(catalog):
        return {
            (entry.msgctxt, entry.msgid): (entry.msgstr, tuple(sorted(entry.msgstr_plural.items())))
            for entry in catalog.translated_entries()
        }

    assert texts(mo) == texts(po)


@pytest.mark.django_db
def test_language_names_follow_the_page(client):
    from django.utils import translation

    from vocabulary.models import Language

    english = Language.objects.get(code="en")
    with translation.override("cs"):
        assert str(english) == "Angličtina"
    with translation.override("en"):
        assert str(english) == "English"


def test_date_formats_follow_the_page():
    from datetime import datetime

    from django.utils import translation
    from django.utils.formats import date_format

    moment = datetime(2026, 10, 8, 14, 5)
    with translation.override("cs"):
        assert date_format(moment, "SHORT_DATETIME_FORMAT") == "8. 10. 2026 14:05"
    with translation.override("en"):
        assert date_format(moment, "SHORT_DATETIME_FORMAT") == "10/8/2026 2:05 PM"


@pytest.mark.django_db
def test_javascript_texts_come_in_the_language_of_the_page(client):
    from django.urls import reverse

    czech = client.get(reverse("javascript-catalog"), HTTP_ACCEPT_LANGUAGE="cs")
    english = client.get(reverse("javascript-catalog"), HTTP_ACCEPT_LANGUAGE="en")

    # The catalog is JSON inside JavaScript, so Czech letters may come as \\u escapes
    hide = json.dumps("Skrýt heslo")[1:-1]
    assert czech.status_code == 200
    assert hide in czech.content.decode()
    assert hide not in english.content.decode()
