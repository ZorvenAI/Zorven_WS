from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0009_add_website_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="address",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Street address of the physical location",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="company",
            name="state_province",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="company",
            name="postal_code",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="company",
            name="country",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
