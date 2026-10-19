from django.contrib import admin

from .models import LexiconEntry, LexiconSense, LexiconTag


class LexiconSenseInline(admin.TabularInline):
    model = LexiconSense
    extra = 0
    fields = ("position", "translation", "note", "sentence", "sentence_native", "tags")


@admin.register(LexiconEntry)
class LexiconEntryAdmin(admin.ModelAdmin):
    """Imported data, mostly for looking (the next import replaces it; edit the file)."""

    list_display = ("word", "part_of_speech", "band", "level", "ipa", "source")
    # "source" shows what each package of new words brought (docs/slovnik.md)
    list_filter = ("source", "part_of_speech", "band", "level", "foreign_code")
    search_fields = ("word", "forms__text", "senses__translation")
    inlines = [LexiconSenseInline]


@admin.register(LexiconTag)
class LexiconTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
