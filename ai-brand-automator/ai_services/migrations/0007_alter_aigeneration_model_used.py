"""Catch up the migration state with the gemini-3.5-flash rename.

The AIGeneration.model_used default was changed from gemini-2.0-flash to
gemini-3.5-flash in the GCP config migration (#509) without a matching
migration, so `makemigrations --check` has been failing on development_main
ever since — which means any later story running that check inherits a
failure it did not cause.

Schema-inert: Django applies a CharField default in Python rather than as a
database DEFAULT, so this alters no column and rewrites no rows. It exists to
make the migration state match the models again.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_services", "0006_alter_chatsession_options_chatsession_is_pinned"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aigeneration",
            name="model_used",
            field=models.CharField(default="gemini-3.5-flash", max_length=100),
        ),
    ]
