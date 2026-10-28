from datetime import timedelta

from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import select_template
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from study import services as study_services
from study import stats
from study.ratings import MAX_INTERVAL, RATINGS
from vocabulary import services as vocabulary_services

# Help pages: (address, tab name). The first one opens for /help/. Each tab has a template
# for each language, templates/help/<language>/<address>.html; English when one is missing.
HELP_TOPICS = [
    ("slovniky", _("Decks")),
    ("slovicka", _("Words")),
    ("test", _("Test")),
    ("prehled", _("Overview and statistics")),
]


def dashboard(request):
    # Start page; it shows data from more apps (decks, study), so it lives here
    roots = vocabulary_services.load_tree(request.user)
    totals = study_services.annotate_deck_counts(roots, request.user)
    # Cards "Co ti včera / naposledy nešlo": the last day with a test before today
    hard = stats.hard_words(request.user) if roots else {"day": None, "items": []}
    today = stats.today_overview(request.user) if roots else None
    return render(
        request,
        "dashboard.html",
        {
            "roots": roots,
            "totals": totals,
            "hard_words": hard["items"],
            "hard_day": hard["day"],
            "yesterday": timezone.localdate() - timedelta(days=1),
            "today": today,
            # Words saved for later, waiting for a translation (a card above the decks)
            "pending_count": vocabulary_services.pending_words(request.user).count(),
            "pending_first": vocabulary_services.pending_words(request.user)[:2],
        },
    )


def help_index(request):
    return redirect("help", topic=HELP_TOPICS[0][0])


def help_page(request, topic):
    topics = dict(HELP_TOPICS)
    if topic not in topics:
        raise Http404
    template = select_template([f"help/{get_language()}/{topic}.html", f"help/en/{topic}.html"])
    return render(
        request,
        template.template.name,
        {
            "topics": HELP_TOPICS,
            "topic": topic,
            "topic_name": topics[topic],
            # Name of the tabs for screen readers; here, because help templates are not scanned
            # by makemessages
            "tabs_label": _("Help sections"),
            # The table of buttons comes from study/ratings.py, so it is always right
            "ratings": RATINGS,
            "max_interval": MAX_INTERVAL,
            "max_depth": vocabulary_services.MAX_DEPTH,
        },
    )
