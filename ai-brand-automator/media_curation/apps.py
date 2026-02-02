"""
Media Curation Service Django App Configuration.

This app provides intelligent media processing and curation capabilities:
- Routing: Determines correct AI model based on MIME type
- Enrichment: Extracts text from video/audio (STT) and images/PDFs (OCR)
- Sanitization: Redacts PII based on tenant configuration
- Normalization: Outputs standardized JSON for RAG indexing
"""

from django.apps import AppConfig


class MediaCurationConfig(AppConfig):
    """Django app configuration for media_curation."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "media_curation"
    verbose_name = "Media Curation Service"

    def ready(self):
        """Initialize app when Django starts."""
        # Import signal handlers if any
        pass
