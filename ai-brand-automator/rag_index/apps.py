"""
RAG Index Service Django Application Configuration.

This service syncs curated documents from media-curation-svc
to Vertex AI Discovery Engine for RAG search capabilities.
"""

from django.apps import AppConfig


class RagIndexConfig(AppConfig):
    """Django app configuration for RAG Index Service."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "rag_index"
    verbose_name = "RAG Index Service"

    def ready(self):
        """Initialize app when Django starts.

        Register DB-to-RAG signal handlers when enabled.
        """
        from django.conf import settings

        if getattr(settings, "RAG_DB_SYNC_ENABLED", False):
            import rag_index.signals  # noqa: F401
