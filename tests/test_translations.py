"""The translations of the app are complete and compiled."""

from pathlib import Path

import polib
import pytest
from django.conf import settings

LOCALE = Path(settings.BASE_DIR) / "locale"
# English is the language of the source texts, so it needs no catalog
TRANSLATED = [code for code, _name in settings.LANGUAGES if code != "en"]


@pytest.mark.parametrize("code", TRANSLATED)
def test_every_text_is_translated(code):
    po = polib.pofile(LOCALE / code / "LC_MESSAGES" / "django.po")

    assert po.untranslated_entries() == []
    assert po.fuzzy_entries() == []


@pytest.mark.parametrize("code", TRANSLATED)
def test_compiled_catalog_is_up_to_date(code):
    # After editing a .po file run: uv run python manage.py compilemessages
    folder = LOCALE / code / "LC_MESSAGES"
    po = polib.pofile(folder / "django.po")
    mo = polib.mofile(folder / "django.mo")

    def texts(catalog):
        return {
            (entry.msgctxt, entry.msgid): (entry.msgstr, tuple(sorted(entry.msgstr_plural.items())))
            for entry in catalog.translated_entries()
        }

    assert texts(mo) == texts(po)
