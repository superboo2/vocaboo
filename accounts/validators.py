"""Django's password rules with the texts of the app (Czech, "ty").

They check the same as Django's; only the messages are different, because Django has some
of them only in English and the Czech ones say "Vaše".
"""

from django.contrib.auth import password_validation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def get_error_message(self):
        return ngettext(
            "The password is too short, it needs at least %(count)d character.",
            "The password is too short, it needs at least %(count)d characters.",
            self.min_length,
        ) % {"count": self.min_length}

    def get_help_text(self):
        return ngettext(
            "At least %(count)d character.", "At least %(count)d characters.", self.min_length
        ) % {"count": self.min_length}


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    def get_error_message(self):
        return _("The password is too similar to your email.")

    def get_help_text(self):
        return _("It must not be similar to your email.")


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def get_error_message(self):
        return _("The password is too common, think of another one.")

    def get_help_text(self):
        return _("It must not be too common.")


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def get_error_message(self):
        return _("The password can't be only numbers.")

    def get_help_text(self):
        return _("It must not be only numbers.")
