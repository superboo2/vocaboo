from django.db import migrations

INITIAL_LANGUAGES = [
    ("cs", "Čeština"),
    ("en", "Angličtina"),
    ("es", "Španělština"),
]


def add_languages(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    for code, name in INITIAL_LANGUAGES:
        Language.objects.get_or_create(code=code, defaults={"name": name})


def remove_languages(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    Language.objects.filter(code__in=[code for code, _ in INITIAL_LANGUAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("vocabulary", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_languages, remove_languages),
    ]
