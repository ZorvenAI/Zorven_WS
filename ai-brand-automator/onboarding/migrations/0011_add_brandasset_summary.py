from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0010_add_company_address_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandasset",
            name="summary",
            field=models.TextField(
                blank=True,
                default="",
                help_text=("Short LLM-generated description of the asset's contents"),
            ),
        ),
    ]
