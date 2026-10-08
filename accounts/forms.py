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
        fields = ["native_language", "default_direction"]
        labels = {"default_direction": _("Výchozí směr testu")}
        help_texts = {"default_direction": _("Předvyplní se v nastavení nového testu.")}
        widgets = {"default_direction": forms.RadioSelect}
