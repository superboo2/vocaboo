from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from dictionary.providers import get_pronunciation, get_suggestions, other_meanings
from study import services as study_services
from study.formatting import czech_plural
from study.models import StudySession

from . import services
from .forms import (
    DeckCreateForm,
    DeckForm,
    DeckMoveForm,
    TermForm,
    TermMoveForm,
    add_service_errors,
)
from .models import Deck, DeckTerm, Term


def _get_deck(request, pk):
    """Deck of the logged in user, other users' decks give 404."""
    queryset = Deck.objects.select_related("foreign_language", "native_language", "parent")
    return get_object_or_404(queryset, pk=pk, owner=request.user)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def deck_create(request):
    """New root deck."""
    form = DeckCreateForm(
        request.POST or None,
        initial={"native_language": request.user.native_language},
    )
    if request.method == "POST" and form.is_valid():
        try:
            deck = services.create_deck(request.user, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Slovník „%(name)s“ je vytvořený.") % {"name": deck.name})
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {"form": form, "title": _("Nový slovník"), "submit_label": _("Vytvořit")},
    )


def _get_sort(request):
    sort = request.GET.get("sort", "added")
    return sort if sort in services.TERM_SORTS else "added"


def deck_detail(request, pk):
    deck = _get_deck(request, pk)
    children = list(deck.children.all())
    sort = _get_sort(request)
    return render(
        request,
        "vocabulary/deck_detail.html",
        {
            "deck": deck,
            "ancestors": services.get_ancestors(deck)[:-1],
            "children": children,
            "can_add_child": services.can_add_child(deck),
            "max_depth": services.MAX_DEPTH,
            "term_form": TermForm(deck=deck),
            "deck_terms": services.list_deck_terms(deck, sort),
            "sort": sort,
            "sorts": services.TERM_SORTS,
        },
    )


def deck_create_child(request, pk):
    parent = _get_deck(request, pk)
    if not services.can_add_child(parent):
        messages.error(
            request,
            _("Slovníky můžou mít nejvýš %(max)d úrovní.") % {"max": services.MAX_DEPTH},
        )
        return redirect("vocabulary:deck_detail", pk=parent.pk)

    form = DeckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            deck = services.create_deck(request.user, parent=parent, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Slovník „%(name)s“ je vytvořený.") % {"name": deck.name})
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("Nový podslovník"),
            "submit_label": _("Vytvořit"),
            "parent": parent,
            "ancestors": services.get_ancestors(parent),
        },
    )


def deck_edit(request, pk):
    deck = _get_deck(request, pk)
    form = DeckForm(
        request.POST or None,
        initial={"name": deck.name, "description": deck.description},
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.update_deck(deck, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Změny jsou uložené."))
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("Upravit slovník"),
            "submit_label": _("Uložit"),
            "deck": deck,
            "ancestors": services.get_ancestors(deck),
        },
    )


def deck_move(request, pk):
    deck = _get_deck(request, pk)
    form = DeckMoveForm(
        request.POST or None,
        targets=services.get_move_targets(deck),
        initial={"target": str(deck.parent_id) if deck.parent_id else ""},
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.move_deck(deck, form.cleaned_data["target"])
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Slovník je přesunutý."))
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("Přesunout slovník"),
            "submit_label": _("Přesunout"),
            "deck": deck,
            "ancestors": services.get_ancestors(deck),
            "help_text": _(
                "Nabízí se jen slovníky se stejným jazykovým párem, kam se strom vejde "
                "(nejvýš %(max)d úrovní)."
            )
            % {"max": services.MAX_DEPTH},
        },
    )


def deck_delete(request, pk):
    deck = _get_deck(request, pk)
    parent_id = deck.parent_id
    if request.method == "POST":
        deck_count, term_count = services.delete_deck(deck)
        text = _("Slovník „%(name)s“ je smazaný (slovníků: %(decks)d, slovíček: %(terms)d).")
        messages.success(
            request, text % {"name": deck.name, "decks": deck_count, "terms": term_count}
        )
        if parent_id:
            return redirect("vocabulary:deck_detail", pk=parent_id)
        return redirect("dashboard")
    return render(
        request,
        "vocabulary/deck_confirm_delete.html",
        {
            "deck": deck,
            "ancestors": services.get_ancestors(deck),
            "child_count": len(services.get_descendant_ids(deck, include_self=False)),
            "term_count": services.count_terms_deleted_with_deck(deck),
        },
    )


@require_POST
def deck_place(request, pk):
    """Drag and drop in the dashboard tree: put the deck under a parent at a given place.

    POST: parent = id of the new parent deck, or empty for the top level; index = place.
    Answers JSON {"ok": true} or {"ok": false, "error": "..."} with status 400.
    """
    deck = _get_deck(request, pk)
    parent_id = request.POST.get("parent", "")
    parent = _get_deck(request, int(parent_id)) if parent_id.isdigit() else None
    try:
        index = int(request.POST.get("index", ""))
    except ValueError:
        error = _("Chybí místo, kam slovník patří.")
        return JsonResponse({"ok": False, "error": error}, status=400)
    try:
        services.place_deck(deck, parent, index)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": " ".join(error.messages)}, status=400)
    return JsonResponse({"ok": True})


@require_POST
def deck_reorder(request, pk, direction):
    deck = _get_deck(request, pk)
    if direction == "up":
        services.move_deck_up(deck)
    elif direction == "down":
        services.move_deck_down(deck)
    else:
        raise Http404

    if _is_htmx(request):
        # Send back only the list, HTMX puts it in place of the old one
        return render(
            request, "vocabulary/_sibling_list.html", {"decks": services.get_siblings(deck)}
        )
    if deck.parent_id:
        return redirect("vocabulary:deck_detail", pk=deck.parent_id)
    return redirect("dashboard")


# Words


def _get_deck_term(request, deck_pk, pk):
    queryset = DeckTerm.objects.select_related(
        "deck__foreign_language", "deck__native_language", "term"
    ).prefetch_related("term__variants")
    return get_object_or_404(queryset, pk=pk, deck_id=deck_pk, deck__owner=request.user)


def _find_duplicates(request, deck):
    return services.find_duplicates(
        deck,
        foreign=request.POST.get("foreign", ""),
        native=request.POST.get("native", ""),
    )


def _term_form_response(request, deck, form, *, added=None, added_variants=(), check=None):
    """Answer for HTMX: the form (with duplicate hints) and the updated word list."""
    sort = _get_sort(request)
    return render(
        request,
        "vocabulary/_term_add_response.html",
        {
            "deck": deck,
            "term_form": form,
            "added": added,
            "added_variants": added_variants,
            "check": check,
            "deck_terms": services.list_deck_terms(deck, sort),
            "sort": sort,
            "sorts": services.TERM_SORTS,
        },
    )


def _fresh_term_form(deck):
    # After sending, the cursor goes back to the first field.
    form = TermForm(deck=deck)
    form.fields["foreign"].widget.attrs["autofocus"] = True
    return form


def search(request):
    """Search in the user's words; HTMX sends only the results while typing."""
    is_htmx = request.headers.get("HX-Request") == "true"
    query = request.GET.get("q", "")
    # The edit (✎) comes back to the page with the search: the dashboard (HTMX tells its
    # address) or the search page
    back = request.get_full_path()
    if is_htmx:
        page = urlsplit(request.headers.get("HX-Current-URL", ""))
        back = page.path + (f"?{page.query}" if page.query else "") or "/"
    context = {
        "query": query,
        "back": back,
        "hits": services.search_terms(request.user, query),
        "too_short": len(query.strip()) < services.SEARCH_MIN_LENGTH,
        "limit": services.SEARCH_LIMIT,
    }
    if is_htmx:
        return render(request, "vocabulary/_search_results.html", context)
    return render(request, "vocabulary/search.html", context)


def _suggestions(request, deck, foreign):
    if not request.user.show_suggestions:
        return None
    # The form field can hold more variants ("hello; hi"), the first one is the word
    word = foreign.split(";")[0]
    return get_suggestions(word, deck.foreign_language.code, deck.native_language.code)


def term_suggest(request, pk):
    """Translation suggestions while the foreign word is typed (HTMX, see _term_suggest.html)."""
    deck = _get_deck(request, pk)
    result = _suggestions(request, deck, request.GET.get("foreign", ""))
    return render(request, "vocabulary/_term_suggest.html", {"deck": deck, "result": result})


@require_POST
def term_check(request, pk):
    """Duplicate hints while the user types (HTMX, see _term_check.html)."""
    deck = _get_deck(request, pk)
    return render(
        request,
        "vocabulary/_term_check.html",
        {"deck": deck, "check": _find_duplicates(request, deck)},
    )


@require_POST
def term_link(request, pk, term_pk):
    """Put an existing word into this deck ("Přidat i sem", "Přidat jako variantu")."""
    deck = _get_deck(request, pk)
    term = get_object_or_404(Term, pk=term_pk, owner=request.user)
    try:
        added, added_variants = services.link_term(
            deck,
            term,
            foreign=request.POST.get("foreign", ""),
            native=request.POST.get("native", ""),
            context_sentence=request.POST.get("context_sentence", ""),
            context_sentence_native=request.POST.get("context_sentence_native", ""),
        )
    except ValidationError as error:
        form = TermForm(request.POST, deck=deck)
        form.is_valid()
        add_service_errors(form, error)
        return _term_form_response(request, deck, form, check=_find_duplicates(request, deck))

    if not _is_htmx(request):
        messages.success(request, _("Slovíčko je přidané."))
        return redirect("vocabulary:deck_detail", pk=deck.pk)
    form = _fresh_term_form(deck)
    return _term_form_response(request, deck, form, added=added, added_variants=added_variants)


@require_POST
def term_add(request, pk):
    """Add a word from the form on the deck page.

    With HTMX the answer is a fresh form plus the updated word list (out of band swap),
    so the user can type the next word right away.
    """
    deck = _get_deck(request, pk)
    form = TermForm(request.POST, deck=deck)
    added = None
    if form.is_valid():
        try:
            added = services.add_term(deck, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)

    if not _is_htmx(request):
        if added is not None:
            messages.success(request, _("Slovíčko je přidané."))
        else:
            messages.error(request, _("Slovíčko se nepodařilo přidat, zkontroluj formulář."))
        return redirect("vocabulary:deck_detail", pk=deck.pk)

    if added is not None:
        form = _fresh_term_form(deck)
        return _term_form_response(request, deck, form, added=added)
    form.fields["foreign"].widget.attrs["autofocus"] = True
    return _term_form_response(request, deck, form, check=_find_duplicates(request, deck))


def term_detail(request, deck_pk, pk):
    """Everything about one word: texts, decks, review state and history (spec 7.1)."""
    deck_term = _get_deck_term(request, deck_pk, pk)
    term = deck_term.term
    in_decks = term.deck_terms.select_related("deck").order_by("deck__name")
    return render(
        request,
        "vocabulary/term_detail.html",
        {
            "deck": deck_term.deck,
            "deck_term": deck_term,
            "term": term,
            "in_decks": in_decks,
            "other_meanings": other_meanings(term),
            "pronunciation": get_pronunciation(
                term.main_foreign, term.foreign_language.code, with_ipa=request.user.show_ipa
            ),
            "history": study_services.term_history(term),
            "ancestors": services.get_ancestors(deck_term.deck),
        },
    )


@require_POST
def term_add_meaning(request, deck_pk, pk):
    """ "+ Učit se i tento význam" on the word page: the same foreign word, other translation."""
    deck_term = _get_deck_term(request, deck_pk, pk)
    translation = request.POST.get("translation", "")
    try:
        added = services.add_term(
            deck_term.deck,
            foreign="; ".join(deck_term.term.foreign_variants),
            native=translation,
            origin=Term.Origin.TRANSLATED,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("Přidáno: %(word)s → %(native)s")
            % {"word": added.term.main_foreign, "native": added.term.main_native},
        )
    return redirect("vocabulary:term_detail", deck_pk=deck_pk, pk=pk)


def _running_test(request):
    """The test the edit was opened from (?test=pk, button ✏️ on the card), or None."""
    pk = request.GET.get("test", "")
    if not pk.isdigit():
        return None
    return StudySession.objects.filter(pk=pk, user=request.user, finished_at__isnull=True).first()


def _back_url(request):
    """Where the edit was opened from (?next=/path, e.g. the word page or the search), so
    saving or cancelling goes back there; only addresses of this site."""
    back = request.GET.get("next", "")
    if back.startswith("/") and url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return back
    return ""


def term_edit(request, deck_pk, pk):
    deck_term = _get_deck_term(request, deck_pk, pk)
    test = _running_test(request)
    back = _back_url(request)
    deck = deck_term.deck
    term = deck_term.term
    initial = {
        "foreign": "; ".join(term.foreign_variants),
        "native": "; ".join(term.native_variants),
        "context_sentence": deck_term.context_sentence,
        "context_sentence_native": deck_term.context_sentence_native,
        "note": term.note,
    }
    form = TermForm(request.POST or None, deck=deck, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.update_term(
                term,
                foreign=data["foreign"],
                native=data["native"],
                note=data["note"],
            )
            services.update_deck_term(
                deck_term,
                context_sentence=data["context_sentence"],
                context_sentence_native=data["context_sentence_native"],
            )
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Změny jsou uložené."))
            if test:
                # Back to the test: the same card comes again, now fixed
                return redirect("study:card", pk=test.pk)
            return redirect(back or reverse("vocabulary:deck_detail", args=[deck.pk]))
    other_decks = term.deck_terms.exclude(pk=deck_term.pk).select_related("deck")
    return render(
        request,
        "vocabulary/term_form.html",
        {
            "form": form,
            "deck": deck,
            "deck_term": deck_term,
            "other_decks": [item.deck for item in other_decks],
            "ancestors": services.get_ancestors(deck),
            "test": test,
            "back": back or reverse("vocabulary:deck_detail", args=[deck.pk]),
            "suggestions": _suggestions(request, deck, form["foreign"].value() or ""),
        },
    )


def terms_move(request, pk):
    """Move or copy chosen words of the deck into another deck.

    GET with ids (from the word list or the word page) shows the words and the deck choice,
    POST does it. The button "action" says what to do: "move" or "copy".
    """
    deck = _get_deck(request, pk)
    data = request.POST if request.method == "POST" else request.GET
    ids = [value for value in data.getlist("ids") if value.isdigit()]
    deck_terms = list(
        DeckTerm.objects.filter(deck=deck, pk__in=ids)
        .select_related("deck", "term")
        .order_by(Lower("term__main_foreign"))
    )
    if not deck_terms:
        messages.error(request, _("Vyber aspoň jedno slovíčko."))
        return redirect("vocabulary:deck_detail", pk=deck.pk)

    targets = services.get_term_move_targets(deck)
    form = TermMoveForm(request.POST or None, targets=targets)
    if request.method == "POST" and form.is_valid():
        target = form.cleaned_data["target"]
        copy = request.POST.get("action") == "copy"
        try:
            done, already = services.move_deck_terms(deck_terms, target, copy=copy)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            words = f"{done} {czech_plural(done, 'slovíčko', 'slovíčka', 'slovíček')}"
            if copy:
                text = _("Přidáno i do „%(deck)s“: %(words)s.")
            else:
                text = _("Přesunuto do „%(deck)s“: %(words)s.")
            text = text % {"deck": target.name, "words": words}
            if already:
                text += " " + _("Už tam bylo: %(count)d.") % {"count": already}
            messages.success(request, text)
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/terms_move.html",
        {
            "deck": deck,
            "deck_terms": deck_terms,
            "form": form,
            "has_targets": bool(targets),
            "ancestors": services.get_ancestors(deck),
        },
    )


def term_remove(request, deck_pk, pk):
    deck_term = _get_deck_term(request, deck_pk, pk)
    deck = deck_term.deck
    if request.method == "POST":
        word = deck_term.term.main_foreign
        deleted = services.remove_term_from_deck(deck_term)
        if deleted:
            text = _("Slovíčko „%(word)s“ je smazané.")
        else:
            text = _("Slovíčko „%(word)s“ je odebrané z tohoto slovníku.")
        messages.success(request, text % {"word": word})
        return redirect("vocabulary:deck_detail", pk=deck.pk)
    other_decks = deck_term.term.deck_terms.exclude(pk=deck_term.pk).select_related("deck")
    return render(
        request,
        "vocabulary/term_confirm_remove.html",
        {
            "deck": deck,
            "deck_term": deck_term,
            "other_decks": [item.deck for item in other_decks],
            "ancestors": services.get_ancestors(deck),
        },
    )
