"""Django's password rules with the texts of the app (Czech, "ty").

They check the same as Django's; only the messages are different, because Django has some
of them only in English and the Czech ones say "Vaše".
"""

from django.contrib.auth import password_validation
from django.utils.translation import gettext as _


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def get_error_message(self):
        return _("Heslo je moc krátké, potřebuje aspoň %(count)d znaků.") % {
            "count": self.min_length
        }

    def get_help_text(self):
        return _("Aspoň %(count)d znaků.") % {"count": self.min_length}


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    def get_error_message(self):
        return _("Heslo je moc podobné tvému e-mailu.")

    def get_help_text(self):
        return _("Nesmí být podobné tvému e-mailu.")


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def get_error_message(self):
        return _("Heslo je moc běžné, vymysli jiné.")

    def get_help_text(self):
        return _("Nesmí být moc běžné.")


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def get_error_message(self):
        return _("Heslo nemůže být jen z čísel.")

    def get_help_text(self):
        return _("Nesmí být jen z čísel.")
