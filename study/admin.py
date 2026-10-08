from django.contrib import admin

from .models import ReviewLog, ReviewState, StudySession


@admin.register(ReviewState)
class ReviewStateAdmin(admin.ModelAdmin):
    list_display = ("term", "direction", "due_at", "last_rating", "correct_streak", "lapses")
    list_filter = ("direction",)
    list_select_related = ("term",)
    raw_id_fields = ("term",)


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ("user", "started_at", "finished_at", "direction", "scope", "answered")
    list_filter = ("direction", "scope")
    raw_id_fields = ("user",)
    filter_horizontal = ("decks",)


@admin.register(ReviewLog)
class ReviewLogAdmin(admin.ModelAdmin):
    list_display = ("reviewed_at", "user", "term", "direction", "rating", "result", "think_ms")
    list_filter = ("direction", "result", "rating")
    list_select_related = ("user", "term")
    raw_id_fields = ("user", "term", "session")
