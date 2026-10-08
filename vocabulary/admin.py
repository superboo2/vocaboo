from django.contrib import admin

from .models import Deck, DeckTerm, Language, Term, TermVariant


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "parent", "foreign_language", "native_language", "position")
    list_filter = ("foreign_language", "native_language")
    search_fields = ("name",)
    raw_id_fields = ("owner", "parent")


class TermVariantInline(admin.TabularInline):
    model = TermVariant
    extra = 0


class DeckTermInline(admin.TabularInline):
    model = DeckTerm
    extra = 0
    raw_id_fields = ("deck",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    """For looking at data. Change words in the app, it keeps the rules (main variant etc.)."""

    list_display = ("main_foreign", "meaning_hint", "owner", "foreign_language", "created_at")
    list_filter = ("foreign_language", "native_language", "origin")
    search_fields = ("main_foreign", "variants__text")
    raw_id_fields = ("owner",)
    inlines = [TermVariantInline, DeckTermInline]
