from django.shortcuts import render

from study import services as study_services
from vocabulary import services as vocabulary_services


def dashboard(request):
    # Start page; it shows data from more apps (decks, study), so it lives here
    roots = vocabulary_services.load_tree(request.user)
    totals = study_services.annotate_deck_counts(roots, request.user)
    return render(request, "dashboard.html", {"roots": roots, "totals": totals})
