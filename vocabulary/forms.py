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
        return f"{obj.label} ({obj.code})"


class DeckCreateForm(forms.Form):
    """New root deck."""

    name = forms.CharField(label=_("Name"), max_length=100)
    foreign_language = LanguageChoiceField(
        queryset=Language.objects.all(),
        label=_("I want to learn"),
        help_text=_("For example, English."),
    )
    native_language = LanguageChoiceField(
        queryset=Language.objects.all(),
        label=_("I speak"),
        help_text=_("The language you translate the words into, for example, Czech."),
    )
    description = forms.CharField(
        label=_("Description"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )

    def clean(self):
        cleaned = super().clean()
        foreign = cleaned.get("foreign_language")
        native = cleaned.get("native_language")
        if foreign and native and foreign == native:
            raise ValidationError(
                _("The language you want to learn and the language you speak must be different.")
            )
        return cleaned


class DeckForm(forms.Form):
    """Name and description: used for a new child deck and for editing."""

    name = forms.CharField(label=_("Name"), max_length=100)
    description = forms.CharField(
        label=_("Description"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class DeckMoveForm(forms.Form):
    """Choose a new parent. Choices keep the order of the tree and show full paths."""

    target = forms.ChoiceField(label=_("Move under"), required=False)

    def __init__(self, *args, targets, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = {str(deck.pk): deck for deck, _path in targets}
        self.fields["target"].choices = [("", _("— top level —"))] + [
            (str(deck.pk), " › ".join(d.name for d in path)) for deck, path in targets
        ]

    def clean_target(self):
        # Empty value means the top level
        value = self.cleaned_data["target"]
        return self.targets.get(value) if value else None


class TermMoveForm(forms.Form):
    """Choose the deck for moving or copying words. Choices show full paths."""

    target = forms.ChoiceField(label=_("To deck"))

    def __init__(self, *args, targets, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = {str(deck.pk): deck for deck, _path in targets}
        self.fields["target"].choices = [("", "—")] + [
            (str(deck.pk), " › ".join(d.name for d in path)) for deck, path in targets
        ]

    def clean_target(self):
        return self.targets[self.cleaned_data["target"]]


# A word with two variants in each language, as the sample of an empty word field ("hello; hi").
# These are words of the language, not texts of the app, so they are not translated. Only the
# languages the dictionary of the app has; add one with each new language.
VARIANT_SAMPLES = {
    "cs": "ahoj; čau",
    "en": "hello; hi",
    "es": "hola; buenas",
}


class TermForm(forms.Form):
    """New word or editing a word. Labels show the languages of the deck."""

    foreign = forms.CharField(max_length=1000)
    native = forms.CharField(max_length=1000)
    context_sentence = forms.CharField(
        label=_("Use in a sentence"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_(
            "The word is found in the sentence automatically. "
            "Mark a different form with braces: He {ran} away."
        ),
    )
    context_sentence_native = forms.CharField(
        label=_("Sentence translation"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_(
            # The braces are an example for the user, not a placeholder (Czech has another word)
            # xgettext:no-python-brace-format
            "Optional, to help understand the sentence. You can mark the word: He ran {away}."
        ),
    )
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    # Fields shown under "Více" (more), the first two are always visible
    more_fields = ("context_sentence", "context_sentence_native", "note")

    def __init__(self, *args, deck, **kwargs):
        super().__init__(*args, **kwargs)
        foreign = self.fields["foreign"]
        native = self.fields["native"]
        foreign.label = f"{deck.foreign_language.label} ({deck.foreign_language.code.upper()})"
        native.label = f"{deck.native_language.label} ({deck.native_language.code.upper()})"
        # The grey sample in an empty field tells how to write variants; it is in the language
        # of the field (a Czech field shows "ahoj; čau" also in a CS → EN deck)
        for field, language in ((foreign, deck.foreign_language), (native, deck.native_language)):
            sample = VARIANT_SAMPLES.get(language.code, "")
            field.help_text = _("Separate more variants with a semicolon")
            if sample:
                field.help_text += f": {sample}"
            field.widget.attrs.update(
                {"autocomplete": "off", "autocapitalize": "none", "placeholder": sample}
            )

    def more_has_values(self):
        """Open the "Více" part when some of its fields are filled or have errors."""
        return any(self[name].value() or self[name].errors for name in self.more_fields)
