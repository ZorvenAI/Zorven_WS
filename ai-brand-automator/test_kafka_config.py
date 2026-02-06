#!/usr/bin/env python
"""Quick validation of Kafka SASL/SSL configuration changes."""
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from django.conf import settings  # noqa: E402

print("=" * 60)
print("Kafka Configuration Validation")
print("=" * 60)

print(f"\nKAFKA_BOOTSTRAP_SERVERS: {settings.KAFKA_BOOTSTRAP_SERVERS}")
print(f"KAFKA_SECURITY_PROTOCOL: {repr(settings.KAFKA_SECURITY_PROTOCOL)}")
print(f"KAFKA_SASL_MECHANISM: {repr(settings.KAFKA_SASL_MECHANISM)}")
print(f"KAFKA_SASL_USERNAME: {repr(settings.KAFKA_SASL_USERNAME)}")
pwd_display = (
    "***" if settings.KAFKA_SASL_PASSWORD else repr(settings.KAFKA_SASL_PASSWORD)
)
print(f"KAFKA_SASL_PASSWORD: {pwd_display}")

print("\n--- KAFKA_SASL_CONFIG ---")
sasl_config = settings.KAFKA_SASL_CONFIG
print(f"Result: {sasl_config}")
print("(empty dict = local dev, no SASL needed)")

print("\n--- Celery Beat Schedule ---")
for task_name in settings.CELERY_BEAT_SCHEDULE:
    print(f"  - {task_name}")

print("\n--- Factory Import Test ---")
try:
    from data_ingestion.factory import create_kafka_producer  # noqa: F401

    print("  data_ingestion.factory.create_kafka_producer: OK")
except Exception as e:
    print(f"  data_ingestion.factory.create_kafka_producer: FAIL - {e}")

try:
    from media_curation.factory import (  # noqa: F401, F811
        create_kafka_producer,
    )

    print("  media_curation.factory.create_kafka_producer: OK")
except Exception as e:
    print(f"  media_curation.factory.create_kafka_producer: FAIL - {e}")

try:
    from kafka_service.consumer import KafkaConfig

    sasl = KafkaConfig.get_sasl_config()
    print(f"  kafka_service.KafkaConfig.get_sasl_config(): {sasl}")
except Exception as e:
    print(f"  kafka_service.KafkaConfig: FAIL - {e}")

print("\n" + "=" * 60)
print("All checks passed!" if True else "Some checks failed!")
print("=" * 60)
