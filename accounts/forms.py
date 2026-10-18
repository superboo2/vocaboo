from django import forms
from django.conf import settings
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
        label=_("I speak"),
        required=False,
        help_text=_("The language you translate your words into. It is filled in for a new deck."),
    )

    class Meta:
        model = User
        fields = [
            "ui_language",
            "native_language",
            "default_direction",
            "show_suggestions",
            "show_other_meanings",
            "autoplay_pronunciation",
            "autoplay_content",
            "show_ipa",
        ]
        labels = {
            "ui_language": _("App language"),
            "default_direction": _("Default test direction"),
            "show_suggestions": _("Suggest translations"),
            "show_other_meanings": _("Show other meanings from the dictionary"),
            "autoplay_pronunciation": _("Play automatically"),
            "autoplay_content": _("What to play"),
            "show_ipa": _("Show written pronunciation (IPA)"),
        }
        help_texts = {
            "ui_language": _("Menus, buttons and help. Your words stay the same."),
            "default_direction": _("It is filled in when you set up a new test."),
            "show_suggestions": _(
                "While you type a foreign word, suggestions from the dictionary show up under "
                "the translation field."
            ),
            "show_other_meanings": _(
                "At the bottom of the back of the card, as many as fit on one line, the rest "
                "after clicking +N. Your own meanings (e.g. palm → dlaň and palma) are always "
                "shown."
            ),
            "autoplay_pronunciation": _(
                "In the direction foreign → native as soon as the card shows up, in the "
                "direction native → foreign after clicking Show. The browser won't read the "
                "very first card of a test until you click on the page for the first time."
            ),
            "autoplay_content": _("If the word has no sentence, the word is played."),
            "show_ipa": _(
                "Under the foreign word on the card and on the word page, e.g. [pɑːm]. "
                "Useful if you can read IPA."
            ),
        }
        widgets = {"default_direction": forms.RadioSelect, "autoplay_content": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The empty choice means "as the browser asks"
        self.fields["ui_language"].choices = [("", _("Same as the browser"))] + list(
            settings.LANGUAGES
        )


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Django's form with the texts of the app (Django's own say "Vaše", the app says "ty")."""

    error_messages = {
        **DjangoPasswordChangeForm.error_messages,
        "password_incorrect": _("Your current password is wrong, try again."),
        "password_mismatch": _("The new passwords don't match."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Current password")
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].help_text = _(
            "At least 8 characters, not only numbers, not too common and not similar to your email."
        )
        self.fields["new_password2"].label = _("New password again")
        self.fields["new_password2"].help_text = _("Once more, to check.")


class LoginForm(AuthenticationForm):
    """Login with the texts of the app; after a wrong try both fields are red and the cursor
    waits in the password field (the e-mail stays filled in)."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("The email or password is wrong. Try again."),
        "inactive": _("This account is turned off."),
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
