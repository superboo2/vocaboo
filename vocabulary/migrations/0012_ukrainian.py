from django.db import migrations

# Same as 0002_initial_languages: the name is saved in Czech, the page shows it translated
UKRAINIAN = ("uk", "Ukrajinština")


def add_ukrainian(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    code, name = UKRAINIAN
    Language.objects.get_or_create(code=code, defaults={"name": name})


def remove_ukrainian(apps, schema_editor):
    Language = apps.get_model("vocabulary", "Language")
    Language.objects.filter(code=UKRAINIAN[0]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("vocabulary", "0011_pending_word"),
    ]

    operations = [
        migrations.RunPython(add_ukrainian, remove_ukrainian),
    ]
