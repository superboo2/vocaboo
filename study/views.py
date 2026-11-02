from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from accounts.views import settings_tabs
from dictionary.providers import get_example_sentence, get_pronunciation
from vocabulary import services as vocabulary_services
from vocabulary.models import Deck, DeckTerm, Term

from . import services, stats
from .cards import build_card
from .forms import StudySetupForm
from .models import ReviewState, StudyDirection, StudyScope, StudySession
from .ratings import RATINGS


def _get_session(request, pk):
    return get_object_or_404(StudySession, pk=pk, user=request.user)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


@require_POST
def study_practice(request):
    """The buttons ▶︎ Practice: a test right away, by the settings of their page. From the
    page of a deck (deck=<id>) only that deck, from the bar the chosen decks (or all)."""
    deck_id = request.POST.get("deck", "")
    if deck_id.isdigit():
        deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
        decks, back = [deck], reverse("vocabulary:deck_detail", args=[deck.pk])
    else:
        decks, back = services.practice_decks(request.user), reverse("dashboard")
    if not decks:
        # No deck yet: the page ▶︎ Practice says what to do first
        return redirect("study:new")
    try:
        session = services.start_practice(request.user, decks)
    except ValidationError as error:
        messages.info(request, error.messages[0])
        return redirect(back)
    return redirect("study:card", pk=session.pk)


def study_new(request):
    """The page ▶︎ Practice: what the buttons ▶︎ Practice start, saved for the user. Without
    a deck it is the tab ▶︎ Practice of the settings (the decks of the button in the bar);
    ?deck=<id> ("Nastavit" under the button of that deck) shows only that deck, without the
    tabs, keeps the decks of the bar button as they are and "Uložit" goes back to the deck."""
    user = request.user
    one_deck = (request.POST if request.method == "POST" else request.GET).get("deck", "")
    deck = get_object_or_404(Deck, pk=one_deck, owner=user) if one_deck.isdigit() else None
    initial = {
        "decks": [deck.pk] if deck else [item.pk for item in services.practice_decks(user)],
        "direction": user.default_direction,
        "scope": user.practice_scope,
        "practice_cards": user.practice_cards,
    }
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None and deck:
        data.setlist("decks", [str(deck.pk)])
    form = StudySetupForm(data, user=user, initial=initial)
    back = reverse("vocabulary:deck_detail", args=[deck.pk]) if deck else reverse("study:new")

    if request.method == "POST" and form.is_valid():
        _save_practice(user, form.cleaned_data, with_decks=deck is None)
        messages.success(request, _("Settings saved."))
        return redirect(back)

    if form.is_bound:
        selected = {int(value) for value in form["decks"].value() or [] if str(value).isdigit()}
    else:
        selected = set(initial["decks"])
    decks = list(
        Deck.objects.filter(owner=user, pk__in=selected).select_related(
            "foreign_language", "native_language"
        )
    )
    form.name_directions(decks)
    context = {
        "form": form,
        "roots": vocabulary_services.load_tree(user),
        "selected": selected,
        "single_deck": deck,
        "subdeck_count": (
            len(vocabulary_services.get_descendant_ids(deck, include_self=False)) if deck else 0
        ),
        "back": back,
        **_scope_context(user, decks, form["direction"].value()),
    }
    if deck is None:
        context.update(settings_tabs("practice"))
        context["practice_note"] = _practice_note()
    return render(request, "study/setup.html", context)


def _practice_note():
    """The small note at the top of the tab ▶︎ Practice, with the two buttons drawn grey
    (only a picture of them, no links), so it is clear which buttons it is about."""
    sample = '<span class="button-sample">▶︎&nbsp;{}</span>'
    return format_html(
        _(
            "Settings of the quick test that the button {bar} at the top in the bar or "
            "{deck} on a deck starts."
        ),
        bar=format_html(sample, _("Practice")),
        deck=format_html(sample, _("Practice deck")),
    )


def _save_practice(user, data, with_decks):
    """Save the choices of the page ▶︎ Practice for the user. The decks only for the button
    in the bar; all top decks ticked are saved as none, so a new deck is in too."""
    user.default_direction = data["direction"]
    user.practice_scope = data["scope"]
    user.practice_cards = data["practice_cards"]
    user.save(update_fields=["default_direction", "practice_scope", "practice_cards"])
    if with_decks:
        chosen = set(data["decks"])
        roots = set(Deck.objects.filter(owner=user, parent__isnull=True))
        user.practice_decks.set([] if roots <= chosen else chosen)


def _scope_context(user, decks, direction):
    """Card counts next to the choices "which cards" of the page ▶︎ Practice."""
    if direction not in StudyDirection.values:
        direction = user.default_direction
    return {"counts": services.card_counts(user, decks, direction)}


def study_counts(request):
    """The parts "direction" and "which cards" of the page ▶︎ Practice again, with the
    languages and the counts for the ticked decks (HTMX, after every change of the form)."""
    decks = Deck.objects.filter(
        owner=request.user,
        pk__in=[value for value in request.GET.getlist("decks") if value.isdigit()],
    ).select_related("foreign_language", "native_language")
    direction = request.GET.get("direction", "")
    form = StudySetupForm(
        user=request.user,
        initial={
            "direction": direction,
            "scope": request.GET.get("scope", StudyScope.DUE),
            "practice_cards": request.GET.get("practice_cards", ""),
        },
    )
    form.name_directions(decks)
    context = {"form": form, **_scope_context(request.user, list(decks), direction)}
    return render(request, "study/_options.html", context)


def _card_context(session, state):
    remaining = services.session_cards(session).count()
    if session.max_cards is not None:
        remaining = min(remaining, session.max_cards - session.answered)
    return {
        "session": session,
        "card": build_card(session, state),
        "remaining": max(remaining, 1),
        # For the bar at the top of the card: answered of answered + remaining
        "progress": round(100 * session.answered / (session.answered + max(remaining, 1))),
        "ratings": RATINGS,
    }


def study_card(request, pk):
    session = _get_session(request, pk)
    state = services.next_card(session)
    if state is None:
        services.finish_session(session)
        return redirect("study:summary", pk=session.pk)
    return render(request, "study/card_page.html", _card_context(session, state))


@require_POST
def study_answer(request, pk):
    """Save the rating of the shown card and send the next card."""
    session = _get_session(request, pk)
    state = get_object_or_404(ReviewState, pk=request.POST.get("state"), term__owner=request.user)
    # The same answer sent twice (double click, slow network) is saved only once
    if request.POST.get("reviews_count") == str(state.reviews_count):
        try:
            services.record_answer(
                session,
                state,
                request.POST.get("rating", ""),
                think_ms=request.POST.get("think_ms"),
                decide_ms=request.POST.get("decide_ms"),
            )
        except (ValidationError, ValueError):
            return HttpResponseBadRequest(_("Invalid answer."))

    next_state = services.next_card(session)
    if next_state is None:
        services.finish_session(session)
        summary_url = reverse("study:summary", args=[session.pk])
        if _is_htmx(request):
            # HTMX loads the summary as a normal page
            return HttpResponse(headers={"HX-Redirect": summary_url})
        return redirect(summary_url)
    if _is_htmx(request):
        return render(request, "study/_card.html", _card_context(session, next_state))
    return redirect("study:card", pk=session.pk)


@require_POST
def study_finish(request, pk):
    session = _get_session(request, pk)
    services.finish_session(session)
    return redirect("study:summary", pk=session.pk)


def study_summary(request, pk):
    session = _get_session(request, pk)
    summary = services.session_summary(session)
    problem_ids = [term.pk for term in summary["problem_terms"]]
    problems = Term.objects.filter(pk__in=problem_ids).prefetch_related("variants")
    order = {pk: index for index, pk in enumerate(problem_ids)}
    return render(
        request,
        "study/summary.html",
        {
            "session": session,
            "summary": summary,
            "problems": sorted(problems, key=lambda term: order[term.pk]),
            "task": _sentence_task(request, session),
        },
    )


def _sentence_task(request, session):
    """The word that does not stick and a form to add a sentence to it (or None)."""
    hard = services.hard_word_without_sentence(session)
    if hard is None:
        return None
    term = hard["deck_term"].term
    pronunciation = get_pronunciation(
        term.main_foreign, term.foreign_language.code, with_ipa=request.user.show_ipa
    )
    return {
        **hard,
        "term": term,
        "dots": services.answer_dots(term),
        "pronunciation": pronunciation,
        "example": get_example_sentence(term),
    }


@require_POST
def study_add_sentence(request, pk, deck_term_pk):
    """Save the sentence (and its translation) from the end of a test; HTMX gets the part back."""
    session = _get_session(request, pk)
    deck_term = get_object_or_404(
        DeckTerm.objects.select_related("term", "deck"), pk=deck_term_pk, deck__owner=request.user
    )
    sentence = request.POST.get("context_sentence", "")
    task = {"deck_term": deck_term, "term": deck_term.term}
    error = ""
    if not sentence.strip():
        error = _("Write at least the sentence in the foreign language.")
    else:
        try:
            vocabulary_services.update_deck_term(
                deck_term,
                context_sentence=sentence,
                context_sentence_native=request.POST.get("context_sentence_native", ""),
            )
        except ValidationError as exception:
            error = " ".join(exception.messages)
    if not _is_htmx(request):
        if error:
            messages.error(request, error)
        else:
            messages.success(request, _("Sentence saved."))
        return redirect("study:summary", pk=session.pk)
    return render(
        request,
        "study/_sentence_task.html",
        {"session": session, "task": task, "saved": not error, "error": error},
    )


@require_POST
def study_retry(request, pk):
    """New test with only the words rated 😕 or 😵 in this one."""
    session = _get_session(request, pk)
    terms = services.session_summary(session)["problem_terms"]
    if not terms:
        messages.info(request, _("There are no wrong words in this test."))
        return redirect("study:summary", pk=session.pk)
    retry = services.start_session(
        request.user, terms=terms, direction=session.direction, scope=StudyScope.ALL
    )
    return redirect("study:card", pk=retry.pk)


# Tabs of the statistics page: (address, name); the first one is /stats/
STATS_TABS = [
    ("", gettext_lazy("Words")),
    ("tests", gettext_lazy("Tests")),
    ("hard", gettext_lazy("What you struggle with")),
]


def study_stats(request, tab=""):
    """Statistics of the user: the numbers at the top, then a tab: words over time, the last
    tests, or the words that do not stick."""
    if tab not in dict(STATS_TABS):
        raise Http404
    tabs = [
        {
            "url": reverse("study:stats_tab", args=[slug]) if slug else reverse("study:stats"),
            "name": name,
            "current": slug == tab,
        }
        for slug, name in STATS_TABS
    ]
    context = {
        "stats": stats.user_statistics(request.user),
        "tab": tab or "words",
        "tabs": tabs,
        "tabs_label": _("Parts of the statistics"),
    }
    return render(request, "study/stats.html", context)


@require_POST
def study_help_seen(request):
    """The user closed the help of the test screen: it does not open by itself any more."""
    if not request.user.seen_test_help:
        request.user.seen_test_help = True
        request.user.save(update_fields=["seen_test_help"])
    return HttpResponse(status=204)
