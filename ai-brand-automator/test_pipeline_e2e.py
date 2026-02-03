#!/usr/bin/env python
"""
End-to-End Pipeline Test Script.

Tests the full flow:
1. data_ingestion (raw-ingestion-topic)
2. media_curation (curation-needed-topic)
3. rag_index (rag-sync-ready-topic)

Usage:
    python test_pipeline_e2e.py
"""

import json
import uuid
import time
from datetime import datetime, timezone
from confluent_kafka import Producer, Consumer, KafkaError


# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = "localhost:9192"  # External port mapped from Docker

# Topics
RAW_INGESTION_TOPIC = "raw-ingestion-topic"
CURATION_NEEDED_TOPIC = "curation-needed-topic"
RAG_SYNC_READY_TOPIC = "rag-sync-ready-topic"
RAG_SYNC_COMPLETED_TOPIC = "rag-sync-completed-topic"


def create_producer():
    """Create a Kafka producer."""
    return Producer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "client.id": "pipeline-test-producer",
        }
    )


def create_consumer(topics: list[str], group_id: str):
    """Create a Kafka consumer."""
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe(topics)
    return consumer


def send_raw_ingestion_event():
    """Send a test event to raw-ingestion-topic."""
    producer = create_producer()

    event_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    # CloudEvents format for data_ingestion
    event = {
        "specversion": "1.0",
        "type": "com.prevision.ingestion.raw",
        "source": "/test-pipeline",
        "id": event_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": {
            "tenant_id": tenant_id,
            "file_id": file_id,
            "trace_id": trace_id,
            "gcs_uri": "gs://onboarding-bucket1/customer-1/test-document.txt",
            "content_type": "text/plain",
            "file_size": 1024,
            "metadata": {
                "source": "test-pipeline",
                "test_run": True,
            },
        },
    }

    print(f"\n{'='*60}")
    print("Sending test event to raw-ingestion-topic")
    print(f"{'='*60}")
    print(f"Event ID: {event_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Tenant ID: {tenant_id}")
    print(f"File ID: {file_id}")

    producer.produce(
        RAW_INGESTION_TOPIC,
        key=file_id.encode(),
        value=json.dumps(event).encode(),
        headers=[
            ("trace_id", trace_id.encode()),
            ("content-type", b"application/cloudevents+json"),
        ],
    )
    producer.flush()

    print(f"✓ Event sent to {RAW_INGESTION_TOPIC}")
    return event_id, trace_id


def send_curation_event():
    """Send test event to curation-needed-topic.

    Simulates data_ingestion output.
    """
    producer = create_producer()

    event_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    # CloudEvents format for media_curation
    event = {
        "specversion": "1.0",
        "type": "com.prevision.curation.needed",
        "source": "/data-ingestion-svc",
        "id": event_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": {
            "tenant_id": tenant_id,
            "file_id": file_id,
            "trace_id": trace_id,
            "gcs_uri": "gs://onboarding-bucket1/customer-1/test-document.txt",
            "content_type": "text/plain",
            "language_code": "en",
            "metadata": {
                "source": "test-pipeline",
                "test_run": True,
            },
        },
    }

    print(f"\n{'='*60}")
    print("Sending test event to curation-needed-topic")
    print(f"{'='*60}")
    print(f"Event ID: {event_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Tenant ID: {tenant_id}")
    print(f"File ID: {file_id}")

    producer.produce(
        CURATION_NEEDED_TOPIC,
        key=file_id.encode(),
        value=json.dumps(event).encode(),
        headers=[
            ("trace_id", trace_id.encode()),
            ("content-type", b"application/cloudevents+json"),
        ],
    )
    producer.flush()

    print(f"✓ Event sent to {CURATION_NEEDED_TOPIC}")
    return event_id, trace_id


def send_rag_sync_event():
    """Send test event to rag-sync-ready-topic.

    Simulates media_curation output.
    """
    producer = create_producer()

    event_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    # CloudEvents format for rag_index
    event = {
        "specversion": "1.0",
        "type": "com.prevision.rag.sync.ready",
        "source": "/media-curation-svc",
        "id": event_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": {
            "tenant_id": tenant_id,
            "file_id": file_id,
            "trace_id": trace_id,
            "action": "UPSERT",
            "processed_gcs_uri": "gs://curated-content/tenant-123/file-456.json",
            "metadata": {
                "source": "test-pipeline",
                "test_run": True,
                "content_type": "application/json",
            },
        },
    }

    print(f"\n{'='*60}")
    print("Sending test event to rag-sync-ready-topic")
    print(f"{'='*60}")
    print(f"Event ID: {event_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Tenant ID: {tenant_id}")
    print(f"File ID: {file_id}")

    producer.produce(
        RAG_SYNC_READY_TOPIC,
        key=file_id.encode(),
        value=json.dumps(event).encode(),
        headers=[
            ("trace_id", trace_id.encode()),
            ("content-type", b"application/cloudevents+json"),
        ],
    )
    producer.flush()

    print(f"✓ Event sent to {RAG_SYNC_READY_TOPIC}")
    return event_id, trace_id


def monitor_topics(duration_seconds: int = 30):
    """Monitor all topics for a specified duration."""
    print(f"\n{'='*60}")
    print(f"Monitoring topics for {duration_seconds} seconds...")
    print(f"{'='*60}")

    topics = [
        CURATION_NEEDED_TOPIC,
        RAG_SYNC_READY_TOPIC,
        RAG_SYNC_COMPLETED_TOPIC,
    ]

    consumer = create_consumer(topics, f"monitor-{uuid.uuid4().hex[:8]}")

    start_time = time.time()
    messages_received = 0

    try:
        while time.time() - start_time < duration_seconds:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Error: {msg.error()}")
                continue

            messages_received += 1
            topic = msg.topic()
            value = json.loads(msg.value().decode())

            print(f"\n📨 Message received on {topic}:")
            print(f"   Event ID: {value.get('id', 'N/A')}")
            print(f"   Type: {value.get('type', 'N/A')}")
            print(f"   Source: {value.get('source', 'N/A')}")
            if "data" in value:
                print(f"   Tenant ID: {value['data'].get('tenant_id', 'N/A')}")
                print(f"   File ID: {value['data'].get('file_id', 'N/A')}")
    finally:
        consumer.close()

    print(f"\n{'='*60}")
    print(f"Monitoring complete. Received {messages_received} messages.")
    print(f"{'='*60}")


def main():
    """Main test function."""
    import sys

    print("\n" + "=" * 60)
    print("       E2E Pipeline Test")
    print("=" * 60)
    print("\nTopics flow:")
    print("  1. raw-ingestion-topic → data_ingestion")
    print("  2. curation-needed-topic → media_curation")
    print("  3. rag-sync-ready-topic → rag_index")
    print("  4. rag-sync-completed-topic (output)")

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "ingestion":
            send_raw_ingestion_event()
        elif command == "curation":
            send_curation_event()
        elif command == "rag":
            send_rag_sync_event()
        elif command == "monitor":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            monitor_topics(duration)
        elif command == "all":
            # Send events to all stages
            send_curation_event()
            time.sleep(1)
            send_rag_sync_event()
        else:
            print(f"Unknown command: {command}")
            print("\nUsage:")
            print(
                "  python test_pipeline_e2e.py ingestion  - Send to raw-ingestion-topic"
            )
            print("  python test_pipeline_e2e.py curation   - curation topic")
            print("  python test_pipeline_e2e.py rag        - rag-sync topic")
            print("  python test_pipeline_e2e.py monitor [s] - Monitor topics")
            print("  python test_pipeline_e2e.py all        - curation + rag")
    else:
        # Default: send a curation event and monitor
        send_curation_event()
        print("\nWaiting 5 seconds for processing...")
        time.sleep(5)
        send_rag_sync_event()
        print("\nMonitoring topics for 20 seconds...")
        monitor_topics(20)


if __name__ == "__main__":
    main()
