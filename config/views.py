from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from study import services as study_services
from study.ratings import MAX_INTERVAL, RATINGS
from vocabulary import services as vocabulary_services

# Help pages: (address, tab name). The first one opens for /help/.
HELP_TOPICS = [
    ("slovniky", _("Slovníky")),
    ("slovicka", _("Slovíčka")),
    ("test", _("Test")),
    ("prehled", _("Přehled a statistiky")),
]


def dashboard(request):
    # Start page; it shows data from more apps (decks, study), so it lives here
    roots = vocabulary_services.load_tree(request.user)
    totals = study_services.annotate_deck_counts(roots, request.user)
    return render(request, "dashboard.html", {"roots": roots, "totals": totals})


def help_index(request):
    return redirect("help", topic=HELP_TOPICS[0][0])


def help_page(request, topic):
    topics = dict(HELP_TOPICS)
    if topic not in topics:
        raise Http404
    return render(
        request,
        f"help/{topic}.html",
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
