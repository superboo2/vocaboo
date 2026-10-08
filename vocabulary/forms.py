from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Language


def add_service_errors(form, error):
    """Show a ValidationError from services.py in the form.

    Errors for fields the form has go to that field, all others go to the top of the form.
    """
    if not hasattr(error, "error_dict"):
        form.add_error(None, error)
        return
    for field, messages in error.message_dict.items():
        target = field if field in form.fields else None
        if field == NON_FIELD_ERRORS:
            target = None
        form.add_error(target, messages)


class LanguageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} ({obj.code})"


class DeckCreateForm(forms.Form):
    """New root deck."""

    name = forms.CharField(label=_("Název"), max_length=100)
    foreign_language = LanguageChoiceField(
        queryset=Language.objects.all(),
        label=_("Chci se naučit"),
        help_text=_("Např. angličtina."),
    )
    native_language = LanguageChoiceField(
        queryset=Language.objects.all(),
        label=_("Mluvím"),
        help_text=_("Jazyk, do kterého si slovíčka překládáš, např. čeština."),
    )
    description = forms.CharField(
        label=_("Popis"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )

    def clean(self):
        cleaned = super().clean()
        foreign = cleaned.get("foreign_language")
        native = cleaned.get("native_language")
        if foreign and native and foreign == native:
            raise ValidationError(
                _("Jazyk, který se chceš naučit, a jazyk, kterým mluvíš, musí být různé.")
            )
        return cleaned


class DeckForm(forms.Form):
    """Name and description: used for a new child deck and for editing."""

    name = forms.CharField(label=_("Název"), max_length=100)
    description = forms.CharField(
        label=_("Popis"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class DeckMoveForm(forms.Form):
    """Choose a new parent. Choices keep the order of the tree and show full paths."""

    target = forms.ChoiceField(label=_("Přesunout pod"), required=False)

    def __init__(self, *args, targets, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = {str(deck.pk): deck for deck, _path in targets}
        self.fields["target"].choices = [("", _("— nejvyšší úroveň —"))] + [
            (str(deck.pk), " › ".join(d.name for d in path)) for deck, path in targets
        ]

    def clean_target(self):
        # Empty value means the top level
        value = self.cleaned_data["target"]
        return self.targets.get(value) if value else None


class TermForm(forms.Form):
    """New word or editing a word. Labels show the languages of the deck."""

    foreign = forms.CharField(max_length=1000)
    native = forms.CharField(max_length=1000)
    context_sentence = forms.CharField(
        label=_("Použití ve větě"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Slovo ve větě najdu sám. Jiný tvar označ závorkami: He {ran} away."),
    )
    context_source = forms.CharField(
        label=_("Zdroj"),
        required=False,
        max_length=50,
        help_text=_("Např. S01E01."),
    )
    meaning_hint = forms.CharField(
        label=_("Rozlišení významu"),
        required=False,
        max_length=100,
        help_text=_("Jen když má slovo víc významů, např. palm: ruka / strom."),
    )
    note = forms.CharField(
        label=_("Poznámka"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    # Fields shown under "Více" (more), the first two are always visible
    more_fields = ("context_sentence", "context_source", "meaning_hint", "note")

    def __init__(self, *args, deck, **kwargs):
        super().__init__(*args, **kwargs)
        foreign = self.fields["foreign"]
        native = self.fields["native"]
        foreign.label = f"{deck.foreign_language.name} ({deck.foreign_language.code.upper()})"
        native.label = f"{deck.native_language.name} ({deck.native_language.code.upper()})"
        foreign.help_text = _("Víc variant odděl středníkem: hello; hi")
        native.help_text = _("Víc variant odděl středníkem: ahoj; čau")
        foreign.widget.attrs.update({"autocomplete": "off", "autocapitalize": "none"})
        native.widget.attrs.update({"autocomplete": "off", "autocapitalize": "none"})

    def more_has_values(self):
        """Open the "Více" part when some of its fields are filled or have errors."""
        return any(self[name].value() or self[name].errors for name in self.more_fields)
