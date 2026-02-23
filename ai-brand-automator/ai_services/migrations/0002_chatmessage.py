import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_services", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("assistant", "Assistant"),
                            ("system", "System"),
                        ],
                        max_length=10,
                    ),
                ),
                ("content", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "thinking",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="AI reasoning/thinking content for display",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_messages",
                        to="ai_services.chatsession",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(
                        fields=["session", "created_at"],
                        name="ai_services__session_created_idx",
                    ),
                ],
            },
        ),
    ]
