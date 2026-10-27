"""Open reports of mistakes from the word pages and tests, with the concepts of the
dictionary they are about. For the next fix round of the dictionary (the AI checks them and
writes a fix package). Only reads; mark the reports resolved in the admin after the package
is deployed.

    uv run python manage.py reported_words
    uv run python manage.py reported_words --output reported.txt
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from dictionary.models import ErrorReport
from dictionary.reports import matching_concepts


class Command(BaseCommand):
    help = "List the open reports of mistakes with the concepts they are about."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Write the list to this file instead of the screen.")

    def handle(self, *args, **options):
        text = "\n\n".join(_describe(report) for report in open_reports())
        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as file:
                file.write(text + "\n" if text else "")
        else:
            self.stdout.write(text or "No open reports.")


def open_reports():
    return ErrorReport.objects.filter(resolved=False).order_by("created_at", "pk")


def _describe(report):
    """One report as a few lines, e.g.

    #3 2026-10-27 EN → CS · translation
      gnarly → hrubý; drsný
      sentence: That was {gnarly}.
      note: spíš drsný
      concepts: gnarly.adjective.1
    """
    day = timezone.localdate(report.created_at).isoformat()
    pair = f"{report.foreign_language.upper()} → {report.native_language.upper()}"
    lines = [
        f"#{report.pk} {day} {pair} · {report.kind}",
        f"  {report.foreign} → {report.native}",
    ]
    if report.sentence:
        lines.append(f"  sentence: {report.sentence}")
    if report.sentence_native:
        lines.append(f"  sentence translation: {report.sentence_native}")
    if report.note:
        lines.append(f"  note: {report.note}")
    lines.append(f"  concepts: {', '.join(matching_concepts(report)) or '-'}")
    return "\n".join(lines)
