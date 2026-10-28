from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.core.exceptions import ValidationError
from django.utils.crypto import constant_time_compare
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
            "show_intervals",
        ]
        labels = {
            "ui_language": _("App language"),
            "default_direction": _("Default test direction"),
            "show_suggestions": _("Suggest translations"),
            "show_other_meanings": _("Show other meanings from the app dictionary"),
            "autoplay_pronunciation": _("Play automatically"),
            "autoplay_content": _("What to play"),
            "show_ipa": _("Show written pronunciation (IPA)"),
            "show_intervals": _("Show when the word comes again"),
        }
        help_texts = {
            "ui_language": _("Menus, buttons and help. Your words stay the same."),
            "default_direction": _("It is filled in when you set up a new test."),
            "show_suggestions": _(
                "While you type a foreign word, suggestions from the app dictionary show up under "
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
            "show_intervals": _(
                "Under the rating buttons of a test, e.g. 10 min, 1 day, 3 days: when the word "
                "comes again after that rating."
            ),
        }
        widgets = {"default_direction": forms.RadioSelect, "autoplay_content": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The empty choice means "as the browser asks"
        self.fields["ui_language"].choices = [("", _("Same as the browser"))] + list(
            settings.LANGUAGES
        )


PASSWORD_HELP = _(
    "At least 8 characters, not only numbers, not too common and not similar to your email."
)


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Django's form with the texts of the app (Django's own say "Vaše", the app says "ty")."""

    error_messages = {
        **DjangoPasswordChangeForm.error_messages,
        "password_incorrect": _("Your current password is wrong, try again."),
        "password_mismatch": _("New passwords do not match."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Current password")
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].help_text = PASSWORD_HELP
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

    # A new account with the right password whose email is not confirmed yet; the login
    # page then sends a new code and opens the page for it
    unverified_user = None

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            self.unverified_user = self.find_unverified_user()
            for field in self.fields.values():
                field.widget.attrs["aria-invalid"] = "true"
            self.fields["username"].widget.attrs.pop("autofocus", None)
            self.fields["password"].widget.attrs["autofocus"] = True
            raise

    def find_unverified_user(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if not email or not password:
            return None
        user = User.objects.filter(
            email__iexact=email, is_active=False, email_verification__isnull=False
        ).first()
        # Only with the right password: nobody else learns that the account exists
        if user is not None and user.check_password(password):
            return user
        return None


class RegistrationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
        help_text=_("We will send you a code to check it."),
    )
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=PASSWORD_HELP,
    )
    password2 = forms.CharField(
        label=_("Password again"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("Once more, to check."),
    )
    invitation = forms.CharField(
        label=_("Invitation code"),
        help_text=_("You got it from the person who invited you."),
    )
    # A trap for robots: people do not see this field, robots fill in every field
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "tabindex": "-1",
                "autocomplete": "off",
                "class": "trap-field",
                "aria-hidden": "true",
            }
        ),
        label="",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.REGISTRATION_CODE:
            del self.fields["invitation"]

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"]).lower()

    def clean_invitation(self):
        code = self.cleaned_data["invitation"].strip().lower()
        if not constant_time_compare(code, settings.REGISTRATION_CODE.strip().lower()):
            raise ValidationError(_("This invitation code is wrong."))
        return code

    def clean_website(self):
        if self.cleaned_data["website"]:
            raise ValidationError(_("Leave this field empty."))
        return ""

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("Passwords do not match."))
        elif password1:
            try:
                # The email is checked too: the password must not be similar to it
                password_validation.validate_password(
                    password1, User(email=cleaned.get("email", ""))
                )
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned


class VerifyForm(forms.Form):
    code = forms.CharField(
        label=_("Code from the email"),
        # 6 digits, or "123 456" copied with a space
        max_length=7,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9 ]*",
                "autofocus": True,
                "class": "code-input",
            }
        ),
    )

    def clean_code(self):
        # A code copied with a space in the middle works too
        code = self.cleaned_data["code"].replace(" ", "")
        if not code.isdigit() or len(code) != 6:
            raise ValidationError(_("The code has 6 digits."))
        return code


class PasswordResetForm(DjangoPasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = _("Email")
        self.fields["email"].help_text = _("The email you log in with.")
        self.fields["email"].widget.attrs["autofocus"] = True


class SetPasswordForm(DjangoSetPasswordForm):
    """A new password after the link from the email, with the texts of the app."""

    error_messages = {
        **DjangoSetPasswordForm.error_messages,
        "password_mismatch": _("New passwords do not match."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].help_text = PASSWORD_HELP
        self.fields["new_password2"].label = _("New password again")
        self.fields["new_password2"].help_text = _("Once more, to check.")
