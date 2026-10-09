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
        fields = ["native_language", "default_direction", "show_suggestions", "show_other_meanings"]
        labels = {
            "default_direction": _("Výchozí směr testu"),
            "show_suggestions": _("Navrhovat překlad"),
            "show_other_meanings": _("Ukazovat další významy ze slovníku"),
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
        }
        widgets = {"default_direction": forms.RadioSelect}
