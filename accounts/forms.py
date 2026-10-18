from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.core.exceptions import ValidationError
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


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Django's form with the texts of the app (Django's own say "Vaše", the app says "ty")."""

    error_messages = {
        **DjangoPasswordChangeForm.error_messages,
        "password_incorrect": _("Současné heslo není správně, zkus to znovu."),
        "password_mismatch": _("Nová hesla se neshodují."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Současné heslo")
        self.fields["new_password1"].label = _("Nové heslo")
        self.fields["new_password1"].help_text = _(
            "Aspoň 8 znaků, ne jen čísla, ne moc běžné a ne podobné tvému e-mailu."
        )
        self.fields["new_password2"].label = _("Nové heslo znovu")
        self.fields["new_password2"].help_text = _("Pro kontrolu ještě jednou.")


class LoginForm(AuthenticationForm):
    """Login with the texts of the app; after a wrong try both fields are red and the cursor
    waits in the password field (the e-mail stays filled in)."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("E-mail nebo heslo není správně. Zkus to znovu."),
        "inactive": _("Tento účet je vypnutý."),
    }

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            for field in self.fields.values():
                field.widget.attrs["aria-invalid"] = "true"
            self.fields["username"].widget.attrs.pop("autofocus", None)
            self.fields["password"].widget.attrs["autofocus"] = True
            raise
