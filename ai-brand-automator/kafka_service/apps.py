"""
Django App Configuration for Kafka Service
"""

from django.apps import AppConfig


class KafkaServiceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kafka_service"
    verbose_name = "Kafka Service"

    def ready(self):
        """
        Called when Django starts.

        We don't auto-start the Kafka consumer here because it should
        be managed by Celery or run as a separate process.
        """
        pass
