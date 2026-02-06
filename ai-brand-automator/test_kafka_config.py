#!/usr/bin/env python
"""Quick validation of Kafka SASL/SSL configuration changes."""
import sys

import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from django.conf import settings  # noqa: E402

failed = False

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
# Redact password before printing
redacted = {k: ("***" if "password" in k else v) for k, v in sasl_config.items()}
print(f"Result: {redacted}")
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
    failed = True

try:
    from media_curation.factory import (  # noqa: F401, F811
        create_kafka_producer,
    )

    print("  media_curation.factory.create_kafka_producer: OK")
except Exception as e:
    print(f"  media_curation.factory.create_kafka_producer: FAIL - {e}")
    failed = True

try:
    from kafka_service.consumer import KafkaConfig

    sasl = KafkaConfig.get_sasl_config()
    # Redact password
    redacted_sasl = {k: ("***" if "password" in k else v) for k, v in sasl.items()}
    print(f"  kafka_service.KafkaConfig.get_sasl_config(): {redacted_sasl}")
except Exception as e:
    print(f"  kafka_service.KafkaConfig: FAIL - {e}")
    failed = True

print("\n" + "=" * 60)
if failed:
    print("Some checks FAILED!")
    print("=" * 60)
    sys.exit(1)
else:
    print("All checks passed!")
    print("=" * 60)
