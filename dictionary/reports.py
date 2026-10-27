"""Reported mistakes of the dictionary: saving a report (word page or test) and finding the
concepts it is about (for the command reported_words)."""

from .models import Concept, ConceptTextForm, ErrorReport, WordSense


def open_report(user, term):
    """The open report of the user for the word, or None."""
    return ErrorReport.objects.filter(user=user, term=term, resolved=False).first()


def report_error(user, deck_term, kind, note=""):
    """Save a report of the word as it is now (with the sentence of this deck). A second
    report of the same word changes the open one."""
    term = deck_term.term
    report = open_report(user, term) or ErrorReport(user=user, term=term)
    report.foreign_language = term.foreign_language.code
    report.native_language = term.native_language.code
    report.foreign = "; ".join(term.foreign_variants)
    report.native = "; ".join(term.native_variants)
    report.sentence = deck_term.context_sentence
    report.sentence_native = deck_term.context_sentence_native
    report.kind = kind
    report.note = note.strip()
    report.save()
    return report


def _variants(text):
    return [part.strip().lower() for part in text.split(";") if part.strip()]


def matching_concepts(report):
    """Keys of the concepts the report is about.

    The concepts of the foreign word (its forms like "palms", or the texts of the foreign
    language); of them the ones whose translation shares a variant with the reported one.
    When none does (the user wrote another translation), all concepts of the word.
    """
    foreign = _variants(report.foreign)
    concept_ids = set(
        WordSense.objects.filter(
            word__forms__text__in=foreign, word__language=report.foreign_language
        ).values_list("concept_id", flat=True)
    )
    concept_ids |= set(
        ConceptTextForm.objects.filter(
            form__in=foreign, text__language=report.foreign_language
        ).values_list("text__concept_id", flat=True)
    )
    matching = set(
        ConceptTextForm.objects.filter(
            text__concept_id__in=concept_ids,
            form__in=_variants(report.native),
            text__language=report.native_language,
        ).values_list("text__concept_id", flat=True)
    )
    return sorted(
        Concept.objects.filter(pk__in=matching or concept_ids).values_list("key", flat=True)
    )
