from django import forms
from django.utils.translation import gettext_lazy as _

from vocabulary.forms import LanguageChoiceField
from vocabulary.models import Language

from .models import User


class SettingsForm(forms.ModelForm):
    native_language = LanguageChoiceField(
        queryset=Language.objects.all(),
        label=_("Mluvím"),
        required=False,
        help_text=_("Jazyk, do kterého si slovíčka překládáš. Předvyplní se u nového slovníku."),
    )

    class Meta:
        model = User
        fields = [
            "native_language",
            "default_direction",
            "show_suggestions",
            "show_other_meanings",
            "show_pronunciation",
            "autoplay_pronunciation",
            "show_ipa",
        ]
        labels = {
            "default_direction": _("Výchozí směr testu"),
            "show_suggestions": _("Navrhovat překlad"),
            "show_other_meanings": _("Ukazovat další významy ze slovníku"),
            "show_pronunciation": _("Ukazovat výslovnost"),
            "autoplay_pronunciation": _("Přehrát výslovnost hned po otočení kartičky"),
            "show_ipa": _("Ukazovat zápis výslovnosti (IPA)"),
        }
        help_texts = {
            "default_direction": _("Předvyplní se v nastavení nového testu."),
            "show_suggestions": _(
                "Když píšeš cizí slovo, pod polem pro překlad se ukážou návrhy ze slovníku "
                "(Wiktionary)."
            ),
            "show_other_meanings": _(
                "Dole na zadní straně kartičky, kolik se vejde na řádek, zbytek po kliknutí "
                "na +N. Tvoje vlastní významy (např. palm → dlaň i palma) se ukazují vždy."
            ),
            "show_pronunciation": _(
                "Výslovnost cizího slova z Wiktionary po otočení kartičky: 🔊 u okraje "
                "(přehraje i klávesa P), u slov bez nahrávky a u vět hlas prohlížeče."
            ),
            "autoplay_pronunciation": _("Jen když je k slovíčku nahrávka."),
            "show_ipa": _(
                "Pod cizím slovem na kartičce a v detailu slovíčka, např. [pɑːm]. "
                "Hodí se, když IPA umíš číst."
            ),
        }
        widgets = {"default_direction": forms.RadioSelect}
