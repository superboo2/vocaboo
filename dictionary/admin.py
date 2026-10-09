from django.contrib import admin

from .models import DictionaryEntry


@admin.register(DictionaryEntry)
class DictionaryEntryAdmin(admin.ModelAdmin):
    """Imported data, for looking only (it is replaced by the next import)."""

    list_display = ("word", "foreign_code", "native_code", "part_of_speech", "source")
    list_filter = ("source", "foreign_code", "native_code")
    search_fields = ("word",)
