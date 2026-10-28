from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from dictionary import reports, topics
from dictionary.providers import get_pronunciation, get_suggestions, other_meanings
from study import services as study_services
from study.models import StudySession

from . import services
from .forms import (
    DeckCreateForm,
    DeckForm,
    DeckMoveForm,
    ErrorReportForm,
    TermForm,
    TermMoveForm,
    add_service_errors,
)
from .models import Deck, DeckTerm, PendingWord, Term


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
            messages.success(request, _("Deck “%(name)s” created.") % {"name": deck.name})
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {"form": form, "title": _("New deck"), "submit_label": _("Create")},
    )


def _get_sort(request):
    sort = request.GET.get("sort", "added")
    return sort if sort in services.TERM_SORTS else "added"


def deck_detail(request, pk):
    deck = _get_deck(request, pk)
    children = list(deck.children.all())
    sort = _get_sort(request)
    # A word for later opened from its list: the usual form, filled with it, the cursor in
    # the translation and the suggestions shown at once
    pending = None
    if request.GET.get("later", "").isdigit():
        pending = PendingWord.objects.filter(
            pk=request.GET["later"], owner=request.user, deck=deck
        ).first()
    term_form = _later_form(deck, pending) if pending is not None else TermForm(deck=deck)
    return render(
        request,
        "vocabulary/deck_detail.html",
        {
            "deck": deck,
            "ancestors": services.get_ancestors(deck)[:-1],
            "children": children,
            "can_add_child": services.can_add_child(deck),
            "max_depth": services.MAX_DEPTH,
            "term_form": term_form,
            "pending": pending,
            "suggest_result": _suggestions(request, deck, pending.foreign) if pending else None,
            "deck_terms": services.list_deck_terms(deck, sort),
            "sort": sort,
            "sorts": services.TERM_SORTS,
            "has_dictionary": topics.has_dictionary(deck),
            "pending_count": services.pending_words(request.user, deck).count(),
            "pending_first": services.pending_words(request.user, deck)[:2],
        },
    )


def _later_form(deck, pending):
    """The usual form filled with a word for later: the cursor in the translation."""
    form = TermForm(
        deck=deck,
        initial={
            "foreign": pending.foreign,
            "context_sentence": pending.context_sentence,
            "note": pending.note,
        },
    )
    form.fields["native"].widget.attrs["autofocus"] = True
    # The filled foreign word lights up for a moment, so it is clear what came in
    form.fields["foreign"].widget.attrs["class"] = "just-filled"
    return form


def topic_words(request, pk):
    """Words of a topic from the dictionary of the app; the ticked ones are added to the deck.

    GET ?topic=zvire&level=A1&level=A2&page=2 shows one page; POST adds the ticked meanings and
    comes back to the same page (the added words are gone from it).
    """
    deck = _get_deck(request, pk)
    if not topics.has_dictionary(deck):
        raise Http404
    tag = topics.find_topic(request.GET.get("topic", ""))
    levels = [level for level in request.GET.getlist("level") if level in topics.LEVELS]
    levels = levels or list(topics.DEFAULT_LEVELS)
    page = int(request.GET["page"]) if request.GET.get("page", "").isdigit() else 1
    # Parts of speech: all groups unless some are chosen
    pos_groups = [key for key in request.GET.getlist("pos") if key in topics.POS_GROUPS]
    pos_groups = pos_groups or list(topics.POS_GROUPS)

    if request.method == "POST" and tag:
        added = topics.add_topic_words(deck, request.POST.getlist("sense"))
        if added:
            messages.success(
                request,
                ngettext(
                    "Added %(count)s word to “%(deck)s”.",
                    "Added %(count)s words to “%(deck)s”.",
                    len(added),
                )
                % {"count": len(added), "deck": deck.name},
            )
        else:
            messages.info(request, _("Tick the words you want to add."))
        return redirect(request.get_full_path())

    show_owned = request.GET.get("owned") == "1"
    if tag:
        words, has_next, counts = topics.topic_words(
            deck, tag, levels, page, show_owned, pos_groups
        )
    else:
        words, has_next, counts = [], False, topics.TopicCounts()
    # E.g. "A1, A2, B1 · nouns" for the line with the number of words (all parts: not named)
    filter_parts = [", ".join(levels)]
    if len(pos_groups) < len(topics.POS_GROUPS):
        filter_parts.append(", ".join(str(topics.POS_GROUPS[key][0]) for key in pos_groups))
    query = request.GET.copy()
    query.pop("page", None)
    # The same choice with or without the words from other decks
    toggle = query.copy()
    toggle.pop("owned", None)
    if not show_owned:
        toggle["owned"] = "1"
    return render(
        request,
        "vocabulary/topic_words.html",
        {
            "deck": deck,
            "ancestors": services.get_ancestors(deck)[:-1],
            "topics": topics.topics(),
            "tag": tag,
            "topic_name": topics.topic_name(tag) if tag else "",
            "levels": topics.LEVELS,
            "chosen_levels": levels,
            "pos_groups": [(key, name) for key, (name, _kinds) in topics.POS_GROUPS.items()],
            "chosen_pos": pos_groups,
            "filter_text": " · ".join(filter_parts),
            "words": words,
            "page": page,
            "has_next": has_next,
            "query": query.urlencode(),
            "page_size": topics.PAGE,
            "counts": counts,
            "show_owned": show_owned,
            "toggle_query": toggle.urlencode(),
        },
    )


def deck_create_child(request, pk):
    parent = _get_deck(request, pk)
    if not services.can_add_child(parent):
        messages.error(
            request,
            _("Decks can have at most %(max)d levels.") % {"max": services.MAX_DEPTH},
        )
        return redirect("vocabulary:deck_detail", pk=parent.pk)

    form = DeckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            deck = services.create_deck(request.user, parent=parent, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, _("Deck “%(name)s” created.") % {"name": deck.name})
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("New sub-deck"),
            "submit_label": _("Create"),
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
            messages.success(request, _("Changes saved."))
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("Edit name and description"),
            "submit_label": _("Save"),
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
            messages.success(request, _("Deck moved."))
            return redirect("vocabulary:deck_detail", pk=deck.pk)
    return render(
        request,
        "vocabulary/deck_form.html",
        {
            "form": form,
            "title": _("Move deck"),
            "submit_label": _("Move"),
            "deck": deck,
            "ancestors": services.get_ancestors(deck),
            "help_text": _(
                "Only decks with the same languages where the tree fits are offered "
                "(at most %(max)d levels)."
            )
            % {"max": services.MAX_DEPTH},
        },
    )


def deck_delete(request, pk):
    deck = _get_deck(request, pk)
    parent_id = deck.parent_id
    if request.method == "POST":
        deck_count, term_count = services.delete_deck(deck)
        text = _("Deck “%(name)s” deleted (decks: %(decks)d, words: %(terms)d).")
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
        error = _("Could not tell where to move the deck. Try again.")
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


def _term_form_response(
    request,
    deck,
    form,
    *,
    added=None,
    added_variants=(),
    check=None,
    saved_later=None,
    pending=None,
    from_later=False,
    suggest_result=None,
):
    """Answer for HTMX: the form (with duplicate hints), the updated word list and the card
    "Odložené"."""
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
            "saved_later": saved_later,
            # The word for later still being added (kept after an error), or one just added
            "pending": pending,
            "from_later": from_later,
            "suggest_result": suggest_result,
            "pending_count": services.pending_words(request.user, deck).count(),
            "pending_first": services.pending_words(request.user, deck)[:2],
            "all_pending_count": services.pending_words(request.user).count(),
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
    word = request.GET.get("foreign", "").strip()
    result = _suggestions(request, deck, word)
    return render(
        request, "vocabulary/_term_suggest.html", {"deck": deck, "result": result, "word": word}
    )


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
        messages.success(request, _("Word added."))
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
    # The word for later the form was filled with (?later=<id> on the deck page)
    pending = PendingWord.objects.filter(
        pk=request.POST.get("later") or 0, owner=request.user, deck=deck
    ).first()
    added = None
    if form.is_valid():
        try:
            added = services.add_term(deck, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
    if added is not None and pending is not None:
        # It has its translation now: it is a word of the deck, no longer waiting
        pending.delete()

    if not _is_htmx(request):
        if added is not None:
            messages.success(request, _("Word added."))
        else:
            messages.error(request, _("The word could not be added, check the form."))
        return redirect("vocabulary:deck_detail", pk=deck.pk)

    if added is not None:
        form = _fresh_term_form(deck)
        return _term_form_response(request, deck, form, added=added, from_later=pending is not None)
    form.fields["foreign"].widget.attrs["autofocus"] = True
    return _term_form_response(
        request, deck, form, check=_find_duplicates(request, deck), pending=pending
    )


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


def term_report(request, deck_pk, pk):
    """ "Report a mistake" on the word page or in a test (?test=pk, button ⚐ on the card):
    what is wrong with the suggested translation or sentence, for the next fix round of the
    dictionary (dictionary.reports). The menu always says "Report a mistake"; when the word
    has an open report, this page says so and changes it. From a test it goes back to the
    same card."""
    deck_term = _get_deck_term(request, deck_pk, pk)
    test = _running_test(request)
    if test:
        back = reverse("study:card", kwargs={"pk": test.pk})
    else:
        back = reverse(
            "vocabulary:term_detail", kwargs={"deck_pk": deck_term.deck_id, "pk": deck_term.pk}
        )
    report = reports.open_report(request.user, deck_term.term)
    initial = {"kind": report.kind, "note": report.note} if report else None
    form = ErrorReportForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        reports.report_error(request.user, deck_term, **form.cleaned_data)
        if report:
            messages.success(request, _("Report updated."))
        else:
            messages.success(request, _("Thanks, the mistake is reported."))
        return redirect(back)
    return render(
        request,
        "vocabulary/term_report.html",
        {
            "deck": deck_term.deck,
            "deck_term": deck_term,
            "term": deck_term.term,
            "form": form,
            "report": report,
            "back": back,
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
            _("Added: %(word)s → %(native)s")
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
            messages.success(request, _("Changes saved."))
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
        messages.error(request, _("Choose at least one word."))
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
            words = ngettext("%(count)s word", "%(count)s words", done) % {"count": done}
            if copy:
                text = _("Also added to “%(deck)s”: %(words)s.")
            else:
                text = _("Moved to “%(deck)s”: %(words)s.")
            text = text % {"deck": target.name, "words": words}
            if already:
                text += " " + _("Already there: %(count)d.") % {"count": already}
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
            text = _("Word “%(word)s” deleted.")
        else:
            text = _("Word “%(word)s” removed from this deck.")
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


# Words for later ("Na později"): a foreign word without a translation, saved from the form
# of a deck and translated later in the same form.


@require_POST
def term_later(request, pk):
    """ "Na později" in the form of a deck: save the foreign word (and its sentence and note)
    without a translation. Answers like adding a word: a fresh form and what was saved."""
    deck = _get_deck(request, pk)
    try:
        pending = services.save_for_later(
            deck,
            foreign=request.POST.get("foreign", ""),
            context_sentence=request.POST.get("context_sentence", ""),
            note=request.POST.get("note", ""),
        )
    except ValidationError as error:
        form = TermForm(request.POST, deck=deck)
        form.is_valid()
        form.errors.pop("native", None)
        add_service_errors(form, error)
        return _term_form_response(request, deck, form)
    if not _is_htmx(request):
        messages.success(request, _("Saved for later: %(word)s") % {"word": pending.foreign})
        return redirect("vocabulary:deck_detail", pk=deck.pk)
    return _term_form_response(request, deck, _fresh_term_form(deck), saved_later=pending)


def term_from_later(request, pk, later_pk):
    """A word in the card "Odložené" on the deck page: the form filled with it (HTMX), so the
    page does not load again and does not move when the form is on the screen."""
    deck = _get_deck(request, pk)
    pending = get_object_or_404(PendingWord, pk=later_pk, owner=request.user, deck=deck)
    if not _is_htmx(request):
        url = reverse("vocabulary:deck_detail", args=[deck.pk])
        return redirect(f"{url}?later={pending.pk}")
    return _term_form_response(
        request,
        deck,
        _later_form(deck, pending),
        pending=pending,
        suggest_result=_suggestions(request, deck, pending.foreign),
    )


def later_list(request):
    """The words for later, of all decks or of one (?deck=<id>). A word opens the usual form
    of its deck, filled with it (deck_detail ?later=<id>)."""
    deck = None
    if request.GET.get("deck", "").isdigit():
        deck = get_object_or_404(Deck, pk=request.GET["deck"], owner=request.user)
    words = services.pending_words(request.user, deck)
    return render(request, "vocabulary/later_list.html", {"deck": deck, "words": words})


def _later_back(request):
    # Back to the list it was sent from (all decks or one)
    deck = request.POST.get("back_deck", "")
    url = reverse("vocabulary:later_list")
    return redirect(f"{url}?deck={deck}" if deck.isdigit() else url)


@require_POST
def later_delete(request, pk):
    pending = get_object_or_404(PendingWord, pk=pk, owner=request.user)
    pending.delete()
    messages.success(request, _("Deleted: %(word)s") % {"word": pending.foreign})
    return _later_back(request)
