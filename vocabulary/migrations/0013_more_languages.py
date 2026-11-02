from django.db import migrations

# Languages for decks only (no translation of the app, no dictionary yet). The names are saved
# in Czech as in 0002_initial_languages; the page shows them translated (LANGUAGE_NAMES).
LANGUAGES = [
    ("de", "Němčina"),
    ("fr", "Francouzština"),
    ("it", "Italština"),
    ("pl", "Polština"),
    ("ru", "Ruština"),
]


def add_languages(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    for code, name in LANGUAGES:
        Language.objects.get_or_create(code=code, defaults={"name": name})


def remove_languages(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    Language.objects.filter(code__in=[code for code, _name in LANGUAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("vocabulary", "0012_ukrainian"),
    ]

    operations = [
        migrations.RunPython(add_languages, remove_languages),
    ]
