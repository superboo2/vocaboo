from django.urls import path

from . import views

app_name = "vocabulary"

urlpatterns = [
    path("search/", views.search, name="search"),
    path("decks/new/", views.deck_create, name="deck_create"),
    path("decks/<int:pk>/", views.deck_detail, name="deck_detail"),
    path("decks/<int:pk>/new/", views.deck_create_child, name="deck_create_child"),
    path("decks/<int:pk>/edit/", views.deck_edit, name="deck_edit"),
    path("decks/<int:pk>/move/", views.deck_move, name="deck_move"),
    path("decks/<int:pk>/delete/", views.deck_delete, name="deck_delete"),
    path("decks/<int:pk>/place/", views.deck_place, name="deck_place"),
    path("decks/<int:pk>/words/add/", views.term_add, name="term_add"),
    path("decks/<int:pk>/words/check/", views.term_check, name="term_check"),
    path("decks/<int:pk>/words/suggest/", views.term_suggest, name="term_suggest"),
    path("decks/<int:pk>/words/link/<int:term_pk>/", views.term_link, name="term_link"),
    path("decks/<int:pk>/words/move/", views.terms_move, name="terms_move"),
    path("decks/<int:deck_pk>/words/<int:pk>/", views.term_detail, name="term_detail"),
    path("decks/<int:deck_pk>/words/<int:pk>/edit/", views.term_edit, name="term_edit"),
    path(
        "decks/<int:deck_pk>/words/<int:pk>/meaning/",
        views.term_add_meaning,
        name="term_add_meaning",
    ),
    path("decks/<int:deck_pk>/words/<int:pk>/remove/", views.term_remove, name="term_remove"),
    path(
        "decks/<int:pk>/reorder/<str:direction>/",
        views.deck_reorder,
        name="deck_reorder",
    ),
]
