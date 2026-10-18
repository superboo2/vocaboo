from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import select_template
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
    # Cards "Co ti nejde" of the last 7 days, the same as on the statistics page
    hard_words = stats.hard_words(request.user) if roots else []
    today = stats.today_overview(request.user) if roots else None
    return render(
        request,
        "dashboard.html",
        {
            "roots": roots,
            "totals": totals,
            "hard_words": hard_words,
            "today": today,
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
            # The table of buttons comes from study/ratings.py, so it is always right
            "ratings": RATINGS,
            "max_interval": MAX_INTERVAL,
            "max_depth": vocabulary_services.MAX_DEPTH,
        },
    )
