"""Data migration: copy ChatSession.messages JSONField → ChatMessage rows."""

from django.db import migrations
from django.utils.dateparse import parse_datetime
from django.utils import timezone


def migrate_messages_forward(apps, schema_editor):
    ChatSession = apps.get_model("ai_services", "ChatSession")
    ChatMessage = apps.get_model("ai_services", "ChatMessage")

    for session in ChatSession.objects.all():
        if not session.messages:
            continue
        messages_to_create = []
        for msg in session.messages:
            role = msg.get("role", "user")
            if role not in ("user", "assistant", "system"):
                role = "user"
            content = msg.get("content", "")
            metadata = msg.get("metadata", {})
            timestamp = msg.get("timestamp")
            created_at = (
                parse_datetime(timestamp) if timestamp else None
            ) or timezone.now()
            messages_to_create.append(
                ChatMessage(
                    session=session,
                    role=role,
                    content=content,
                    metadata=metadata,
                    created_at=created_at,
                )
            )
        if messages_to_create:
            ChatMessage.objects.bulk_create(messages_to_create)


def migrate_messages_backward(apps, schema_editor):
    ChatSession = apps.get_model("ai_services", "ChatSession")
    ChatMessage = apps.get_model("ai_services", "ChatMessage")

    for session in ChatSession.objects.all():
        messages = []
        for msg in ChatMessage.objects.filter(session=session).order_by("created_at"):
            messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                    "metadata": msg.metadata,
                }
            )
        session.messages = messages
        session.save()


class Migration(migrations.Migration):

    dependencies = [
        ("ai_services", "0002_chatmessage"),
    ]

    operations = [
        migrations.RunPython(
            migrate_messages_forward,
            migrate_messages_backward,
        ),
    ]
