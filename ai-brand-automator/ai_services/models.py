from django.db import models
from django.utils import timezone
from tenants.models import Tenant


class ChatSession(models.Model):
    """
    AI chat sessions for brand strategy conversations
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    session_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique session identifier",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Session title",
    )

    # Chat data
    messages = models.JSONField(default=list, help_text="List of chat messages")
    context = models.JSONField(
        default=dict, help_text="Session context (company info, etc.)"
    )

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"
        ordering = ["-last_activity"]

    def __str__(self):
        return f"{self.title or 'Chat Session'} ({self.tenant.name})"

    def add_message(self, role, content, metadata=None):
        """Add a message to the session (legacy JSONField method).

        Prefer creating ChatMessage objects directly for new code.
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": timezone.now().isoformat(),
            "metadata": metadata or {},
        }
        self.messages.append(message)
        self.last_activity = timezone.now()
        self.save()


class ChatMessage(models.Model):
    """Individual chat message — replaces ChatSession.messages JSONField.

    Enables proper pagination, querying by role, indexing, and richer
    per-message metadata (thinking, attachments) that a JSONField cannot
    efficiently support.
    """

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    thinking = models.TextField(
        blank=True,
        default="",
        help_text="AI reasoning/thinking content for display",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class SessionAttachment(models.Model):
    """File attached to a chat message, processed through data pipeline."""

    PIPELINE_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("indexed", "Indexed"),
        ("failed", "Failed"),
    ]

    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    asset = models.ForeignKey(
        "onboarding.BrandAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_attachments",
    )
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.PositiveIntegerField(default=0)
    pipeline_status = models.CharField(
        max_length=20,
        choices=PIPELINE_STATUS_CHOICES,
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.pipeline_status})"


class AIGeneration(models.Model):
    """
    Track AI content generations
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="ai_generations"
    )

    content_type = models.CharField(
        max_length=50,
        choices=[
            ("brand_strategy", "Brand Strategy"),
            ("brand_identity", "Brand Identity"),
            ("content", "Content Generation"),
            ("analysis", "Market Analysis"),
        ],
        help_text="Type of AI-generated content",
    )

    prompt = models.TextField(help_text="AI prompt used")
    response = models.TextField(help_text="AI response generated")
    tokens_used = models.PositiveIntegerField(
        default=0, help_text="API tokens consumed"
    )

    # Metadata
    model_used = models.CharField(max_length=100, default="gemini-2.0-flash-exp")
    created_at = models.DateTimeField(default=timezone.now)
    processing_time = models.FloatField(
        default=0.0, help_text="Processing time in seconds"
    )

    class Meta:
        verbose_name = "AI Generation"
        verbose_name_plural = "AI Generations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.content_type} - {self.tenant.name} ({self.created_at.date()})"
