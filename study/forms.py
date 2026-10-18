from django import forms
from django.utils.translation import gettext_lazy as _

from vocabulary.models import Deck

from .models import StudyDirection, StudyScope


class StudySetupForm(forms.Form):
    """Settings of a new test (spec 6.1). The deck tree is drawn by the template."""

    decks = forms.ModelMultipleChoiceField(
        queryset=Deck.objects.none(),
        label=_("Decks"),
        error_messages={"required": _("Choose at least one deck.")},
    )
    direction = forms.ChoiceField(
        label=_("Direction"), choices=StudyDirection.choices, widget=forms.RadioSelect
    )
    scope = forms.ChoiceField(
        label=_("Which cards"),
        choices=StudyScope.choices,
        widget=forms.RadioSelect,
        initial=StudyScope.DUE,
    )
    max_cards = forms.IntegerField(
        label=_("Max cards"),
        required=False,
        min_value=1,
        max_value=1000,
        help_text=_("Empty = no limit."),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["decks"].queryset = Deck.objects.filter(owner=user)
