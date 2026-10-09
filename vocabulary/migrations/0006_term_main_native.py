"""Words are told apart by their translation instead of a meaning hint.

1. New field main_native (copy of the main translation), filled from the variants.
2. Meaning hints are kept: they move to the note of the word.
3. The unique constraint uses main_native, the field meaning_hint is removed.
"""

import django.db.models.functions.text
from django.db import migrations, models
from django.db.models import F

# Hint written automatically by older seed_demo; it means nothing, so it is not kept
EMPTY_HINT = "jiný význam"


def fill_main_native(apps, schema_editor):
    Term = apps.get_model("vocabulary", "Term")
    TermVariant = apps.get_model("vocabulary", "TermVariant")
    for term in Term.objects.all():
        main = (
            TermVariant.objects.filter(term=term, side="N").order_by("position").first()
        )
        term.main_native = main.text if main else ""
        hint = term.meaning_hint.strip()
        if hint and hint != EMPTY_HINT:
            term.note = f"{hint}\n{term.note}".strip() if term.note else hint
        term.save(update_fields=["main_native", "note"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_language_labels"),
        ("vocabulary", "0005_language_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="term",
            name="main_native",
            field=models.CharField(default="", max_length=200, verbose_name="hlavní překlad"),
            preserve_default=False,
        ),
        migrations.RunPython(fill_main_native, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="term", name="unique_term"),
        migrations.RemoveField(model_name="term", name="meaning_hint"),
        migrations.AddConstraint(
            model_name="term",
            constraint=models.UniqueConstraint(
                F("owner"),
                F("foreign_language"),
                F("native_language"),
                django.db.models.functions.text.Lower("main_foreign"),
                django.db.models.functions.text.Lower("main_native"),
                name="unique_term",
                violation_error_message="Toto slovíčko už máš.",
            ),
        ),
    ]
