from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Concept,
    ConceptText,
    ErrorReport,
    LexiconPackage,
    LexiconTag,
    LexiconWord,
    WordForm,
    WordSense,
)

# Imported data, mostly for looking: the next import replaces it, so edit the files
# (docs/slovnik.md). "source" shows what each package of new words brought.


class ConceptTextInline(admin.TabularInline):
    model = ConceptText
    extra = 0
    fields = ("language", "words", "note", "sentence")


class ConceptSenseInline(admin.TabularInline):
    model = WordSense
    extra = 0
    fields = ("word", "position")
    raw_id_fields = ("word",)
    verbose_name_plural = _("dictionary words")


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("key", "source")
    list_filter = ("source", "tags")
    search_fields = ("key", "texts__words", "texts__sentence")
    filter_horizontal = ("tags",)
    inlines = [ConceptTextInline, ConceptSenseInline]


class WordFormInline(admin.TabularInline):
    model = WordForm
    extra = 0


class WordSenseInline(admin.TabularInline):
    model = WordSense
    extra = 0
    fields = ("position", "concept")
    raw_id_fields = ("concept",)


@admin.register(LexiconWord)
class LexiconWordAdmin(admin.ModelAdmin):
    list_display = ("word", "language", "part_of_speech", "band", "level", "ipa", "source")
    list_filter = ("source", "language", "part_of_speech", "band", "level")
    search_fields = ("word", "forms__text")
    inlines = [WordSenseInline, WordFormInline]


@admin.register(LexiconPackage)
class LexiconPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "applied_at")


@admin.register(LexiconTag)
class LexiconTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")


@admin.register(ErrorReport)
class ErrorReportAdmin(admin.ModelAdmin):
    """Mistakes the users reported on the word page (dictionary.reports); the command
    reported_words lists the open ones for the next fix round."""

    list_display = (
        "foreign",
        "native",
        "kind",
        "foreign_language",
        "user",
        "created_at",
        "resolved",
    )
    list_filter = ("resolved", "kind", "foreign_language")
    search_fields = ("foreign", "native", "note")
    raw_id_fields = ("user", "term")
    actions = ["mark_resolved"]

    @admin.action(description=_("Mark as resolved"))
    def mark_resolved(self, request, queryset):
        queryset.update(resolved=True)
