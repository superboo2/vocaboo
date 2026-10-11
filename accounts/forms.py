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
            "autoplay_pronunciation",
            "autoplay_content",
            "show_ipa",
        ]
        labels = {
            "default_direction": _("Výchozí směr testu"),
            "show_suggestions": _("Navrhovat překlad"),
            "show_other_meanings": _("Ukazovat další významy ze slovníku"),
            "autoplay_pronunciation": _("Přehrát automaticky"),
            "autoplay_content": _("Co přehrát"),
            "show_ipa": _("Ukazovat zápis výslovnosti (IPA)"),
        }
        help_texts = {
            "default_direction": _("Předvyplní se v nastavení nového testu."),
            "show_suggestions": _(
                "Když píšeš cizí slovo, pod polem pro překlad se ukážou návrhy ze slovníku."
            ),
            "show_other_meanings": _(
                "Dole na zadní straně kartičky, kolik se vejde na řádek, zbytek po kliknutí "
                "na +N. Tvoje vlastní významy (např. palm → dlaň i palma) se ukazují vždy."
            ),
            "autoplay_pronunciation": _(
                "Ve směru cizí → rodný hned, jak se kartička ukáže, ve směru rodný → cizí po "
                "kliknutí na Ukázat. Úplně první kartičku testu prohlížeč přečíst nedovolí, "
                "dokud na stránce poprvé neklikneš."
            ),
            "autoplay_content": _("Když slovíčko větu nemá, přehraje se slovo."),
            "show_ipa": _(
                "Pod cizím slovem na kartičce a v detailu slovíčka, např. [pɑːm]. "
                "Hodí se, když IPA umíš číst."
            ),
        }
        widgets = {"default_direction": forms.RadioSelect, "autoplay_content": forms.RadioSelect}
