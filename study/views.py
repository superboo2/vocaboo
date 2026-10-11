from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from dictionary.providers import get_example_sentence, get_pronunciation
from vocabulary import services as vocabulary_services
from vocabulary.models import DeckTerm, Term

from . import services
from .cards import build_card
from .forms import StudySetupForm
from .models import ReviewState, StudyScope, StudySession
from .ratings import RATINGS


def _get_session(request, pk):
    return get_object_or_404(StudySession, pk=pk, user=request.user)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def study_new(request):
    """Settings of a new test. ?deck=<id> chooses that deck in advance."""
    initial = {"direction": request.user.default_direction, "scope": StudyScope.DUE}
    if request.GET.get("deck", "").isdigit():
        initial["decks"] = [int(request.GET["deck"])]
    form = StudySetupForm(request.POST or None, user=request.user, initial=initial)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            session = services.start_session(
                request.user,
                data["decks"],
                direction=data["direction"],
                scope=data["scope"],
                max_cards=data["max_cards"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("study:card", pk=session.pk)

    if form.is_bound:
        selected = {int(value) for value in form["decks"].value() or [] if str(value).isdigit()}
    else:
        selected = set(initial.get("decks", []))
    return render(
        request,
        "study/setup.html",
        {"form": form, "roots": vocabulary_services.load_tree(request.user), "selected": selected},
    )


def _card_context(session, state):
    remaining = services.session_cards(session).count()
    if session.max_cards is not None:
        remaining = min(remaining, session.max_cards - session.answered)
    return {
        "session": session,
        "card": build_card(session, state),
        "remaining": max(remaining, 1),
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
            return HttpResponseBadRequest(_("Neplatná odpověď."))

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
        error = _("Napiš aspoň větu v cizím jazyce.")
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
            messages.success(request, _("Věta je uložená."))
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
        messages.info(request, _("V tomto testu nejsou žádná chybná slovíčka."))
        return redirect("study:summary", pk=session.pk)
    retry = services.start_session(
        request.user, terms=terms, direction=session.direction, scope=StudyScope.ALL
    )
    return redirect("study:card", pk=retry.pk)
