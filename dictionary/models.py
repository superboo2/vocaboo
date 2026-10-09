from django.db import models
from django.db.models import F
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class DictionaryEntry(models.Model):
    """One word of an imported dictionary, used only for translation suggestions.

    It is reference data, separate from the words of the users. Filled by the command
    import_wiktionary; importing again replaces all rows of the same source.
    """

    # Where the entry comes from, e.g. "cswiktionary"
    source = models.CharField(_("zdroj"), max_length=30)
    # ISO 639-1 codes: the word is in foreign_code, its meanings are in native_code
    foreign_code = models.CharField(_("jazyk slova"), max_length=2)
    native_code = models.CharField(_("jazyk významů"), max_length=2)
    word = models.CharField(_("slovo"), max_length=200)
    # Part of speech as the source writes it, e.g. "podstatné jméno"
    part_of_speech = models.CharField(_("slovní druh"), max_length=50, blank=True)
    # List of {"text": "dárek", "examples": ["..."]}
    senses = models.JSONField(_("významy"), default=list)
    ipa = models.CharField(_("výslovnost"), max_length=200, blank=True)
    # Recording of the pronunciation (for text to speech later)
    audio_url = models.URLField(_("nahrávka"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("heslo slovníku")
        verbose_name_plural = _("hesla slovníku")
        indexes = [
            # Lookup by word (any letter case) and language pair
            models.Index(
                Lower("word"), F("foreign_code"), F("native_code"), name="dictionary_lookup"
            ),
        ]

    def __str__(self):
        return f"{self.word} ({self.foreign_code} → {self.native_code}, {self.part_of_speech})"
