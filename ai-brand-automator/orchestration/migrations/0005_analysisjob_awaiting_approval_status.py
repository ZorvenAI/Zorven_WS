"""Add AWAITING_APPROVAL status to AnalysisJob.

Required by Ad Publishing Agent (APA-3.3) human approval gate.
This is a non-terminal status — callbacks can still update the job.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orchestration", "0004_trendnotification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="analysisjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("awaiting_approval", "Awaiting Approval"),
                ],
                db_index=True,
                default="queued",
                max_length=20,
            ),
        ),
    ]
