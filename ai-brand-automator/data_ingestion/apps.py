"""Django app configuration for data_ingestion."""

from django.apps import AppConfig


class DataIngestionConfig(AppConfig):
    """Configuration for the Data Ingestion app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "data_ingestion"
    verbose_name = "Data Ingestion Pipeline"

    def ready(self) -> None:
        """Initialize app when Django starts."""
        # Import signals or perform startup tasks here if needed
        pass
