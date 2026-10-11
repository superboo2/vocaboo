from django.urls import path

from . import views

app_name = "study"

urlpatterns = [
    path("study/new/", views.study_new, name="new"),
    path("stats/", views.study_stats, name="stats"),
    path("study/<int:pk>/", views.study_card, name="card"),
    path("study/<int:pk>/answer/", views.study_answer, name="answer"),
    path("study/<int:pk>/finish/", views.study_finish, name="finish"),
    path("study/<int:pk>/summary/", views.study_summary, name="summary"),
    path("study/<int:pk>/retry/", views.study_retry, name="retry"),
    path(
        "study/<int:pk>/sentence/<int:deck_term_pk>/",
        views.study_add_sentence,
        name="add_sentence",
    ),
]
