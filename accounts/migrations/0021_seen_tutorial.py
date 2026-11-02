from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0020_ui_language_more"),
    ]

    operations = [
        # Users from before know the app: they get True and never see the guide by itself
        migrations.AddField(
            model_name="user",
            name="seen_tutorial",
            field=models.BooleanField(default=True, verbose_name="has seen the guide"),
        ),
        # New users get False: the guide opens on their first overview
        migrations.AlterField(
            model_name="user",
            name="seen_tutorial",
            field=models.BooleanField(default=False, verbose_name="has seen the guide"),
        ),
    ]
