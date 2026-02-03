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

        Import signal handlers and perform any startup tasks.
        """
        # Import signal handlers if needed
