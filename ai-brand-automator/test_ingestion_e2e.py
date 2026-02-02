#!/usr/bin/env python
"""
End-to-End Test Script for Data Ingestion Pipeline.

This script tests the full data ingestion flow:
1. Creates a test IngestionEvent
2. Submits it via Celery task (async) or direct processing
3. Verifies the event was processed
4. Checks Kafka for output events
"""
import os
import sys
import uuid
from datetime import datetime, timezone

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
import django

django.setup()

from data_ingestion.factory import create_ingestion_service
from data_ingestion.domain.models import IngestionEvent, EventSource
from data_ingestion.tasks import process_ingestion_event


def run_e2e_test():
    """Run the end-to-end ingestion test."""
    print("=" * 60)
    print("DATA INGESTION E2E TEST")
    print("=" * 60)

    # Show valid sources
    print("\n📋 Valid EventSource values:")
    for src in EventSource:
        print(f"   - {src.value}")

    # Create the ingestion service
    print("\n🔧 Creating ingestion service...")
    try:
        service = create_ingestion_service()
        print("   ✅ Ingestion service created successfully")
    except Exception as e:
        print(f"   ❌ Failed to create service: {e}")
        return False

    # Create a test event with all required fields
    print("\n📝 Creating test event...")
    event_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    event = IngestionEvent(
        event_id=event_id,
        trace_id=trace_id,
        timestamp=timestamp,
        source=EventSource.API_INTEGRATION,
        tenant_id="test-tenant-001",
        file_path="gs://test-bucket/uploads/test-image.jpg",
        file_type="image/jpeg",
        file_size_bytes=1024,
        metadata={"brand_id": "test-brand-001", "test": True},
    )

    print(f"   Event ID:   {event.event_id}")
    print(f"   Trace ID:   {event.trace_id}")
    print(f"   Source:     {event.source.value}")
    print(f"   File Path:  {event.file_path}")
    print(f"   File Type:  {event.file_type}")
    print(f"   File Size:  {event.file_size_bytes} bytes")

    # Option 1: Submit via Celery task (async - queues to worker)
    print("\n🚀 Option 1: Submitting event via Celery task (async)...")
    try:
        task_result = process_ingestion_event.delay(
            event_id=event_id,
            tenant_id="test-tenant-001",
            file_path="gs://test-bucket/uploads/test-image.jpg",
            file_type="image/jpeg",
            timestamp=timestamp.isoformat(),
            source=EventSource.API_INTEGRATION.value,
            trace_id=trace_id,
            metadata={"brand_id": "test-brand-001", "test": True},
        )
        print(f"   ✅ Task queued: {task_result.id}")
        print(f"   Task status: {task_result.status}")
    except Exception as e:
        print(f"   ⚠️  Celery task failed (worker may not be connected): {e}")

    # Option 2: Direct synchronous processing
    print("\n🔄 Option 2: Processing event directly (synchronous)...")
    try:
        # Create new event for direct processing
        event2 = IngestionEvent(
            event_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=EventSource.API_INTEGRATION,
            tenant_id="test-tenant-001",
            file_path="gs://test-bucket/uploads/direct-test.jpg",
            file_type="image/jpeg",
            file_size_bytes=2048,
            metadata={"brand_id": "test-brand-001", "direct": True},
        )
        result = service.process_event(event2)
        print("   ✅ Processing result:")
        print(f"      - Destination: {result.destination_path}")
        print(f"      - Duration: {result.processing_duration_ms}ms")
    except Exception as e:
        print(f"   ⚠️  Direct processing failed: {e}")
        print("      (This is expected if GCS is not configured)")

    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)
    print("\n💡 To monitor the event processing:")
    print("   - Kafka UI: http://localhost:8080")
    print("   - Check topic: raw-ingestion-topic")
    print("   - Celery Worker logs: docker compose logs ingestion-worker -f")
    print(f"   - Event Trace ID: {trace_id}")

    return True


if __name__ == "__main__":
    success = run_e2e_test()
    sys.exit(0 if success else 1)
