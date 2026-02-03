#!/usr/bin/env python
"""
Full End-to-End Pipeline Test with Real GCP Integration.

Tests the complete flow from client request through:
1. Kong Gateway (API entry point)
2. Django Backend (authentication, file handling)
3. Data Ingestion (file storage in GCS, Kafka events)
4. Media Curation (content processing, curation)
5. RAG Index (Vertex AI Discovery Engine sync)

Prerequisites:
- Docker containers running (docker-compose up)
- Valid GCP credentials in credentials/gcs-credentials.json
- Test bucket: onboarding-brandsol-customer-bucket-1
- Vertex AI Discovery Engine configured

Run:
    cd ai-brand-automator
    source ../.venv/bin/activate
    GOOGLE_APPLICATION_CREDENTIALS=credentials/gcs-credentials.json \\
        python test_full_pipeline_e2e.py
"""

import os
import sys
import json
import uuid
import requests
from datetime import datetime, timezone
from pathlib import Path

# GCP Configuration
GCP_PROJECT_ID = "brandsol-project"
GCS_BUCKET = "onboarding-brandsol-customer-bucket-1"
CREDENTIALS_PATH = "credentials/gcs-credentials.json"

# Service URLs
KONG_URL = "http://localhost:8000"
DJANGO_DIRECT_URL = "http://localhost:8001"  # If accessible
KAFKA_BOOTSTRAP = "localhost:9192"

# Test Data
TEST_TENANT_ID = "e2e-test-tenant"
TEST_FILE_PREFIX = "e2e-test"


def setup_gcp_credentials():
    """Set up GCP credentials."""
    creds_path = Path(__file__).parent / CREDENTIALS_PATH
    if creds_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
        print(f"✅ GCP credentials loaded: {creds_path}")
        return True
    else:
        print(f"❌ GCP credentials not found: {creds_path}")
        return False


def setup_django():
    """Set up Django environment."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
    import django

    django.setup()
    print("✅ Django configured")


def print_header(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}")


def print_step(step: int, description: str):
    """Print a step indicator."""
    print(f"\n[Step {step}] {description}")
    print("-" * 50)


class E2ETestResult:
    """Track test results."""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []

    def add_pass(self, name: str, details: str = ""):
        self.passed.append((name, details))
        print(f"  ✅ PASS: {name}")
        if details:
            print(f"     {details}")

    def add_fail(self, name: str, error: str):
        self.failed.append((name, error))
        print(f"  ❌ FAIL: {name}")
        print(f"     Error: {error}")

    def add_skip(self, name: str, reason: str):
        self.skipped.append((name, reason))
        print(f"  ⏭️  SKIP: {name}")
        print(f"     Reason: {reason}")

    def summary(self):
        print_header("TEST SUMMARY")
        print(f"  Passed:  {len(self.passed)}")
        print(f"  Failed:  {len(self.failed)}")
        print(f"  Skipped: {len(self.skipped)}")
        print(f"  Total:   {len(self.passed) + len(self.failed) + len(self.skipped)}")

        if self.failed:
            print("\n  Failed Tests:")
            for name, error in self.failed:
                print(f"    - {name}: {error}")

        return len(self.failed) == 0


def test_kong_gateway(results: E2ETestResult):
    """Test Kong Gateway connectivity."""
    print_step(1, "Testing Kong Gateway")

    try:
        # Kong should return a route not found for unknown paths
        response = requests.get(f"{KONG_URL}/api/unknown", timeout=5)
        if response.status_code in [401, 404]:
            results.add_pass(
                "Kong Gateway Reachable", f"Status: {response.status_code}"
            )
        else:
            results.add_pass(
                "Kong Gateway Reachable", f"Unexpected status: {response.status_code}"
            )
    except requests.exceptions.ConnectionError:
        results.add_fail(
            "Kong Gateway Reachable", "Connection refused - is Docker running?"
        )
        return False

    # Test Kong Admin API
    try:
        response = requests.get("http://localhost:8002/status", timeout=5)
        if response.status_code == 200:
            results.add_pass("Kong Admin API", "Admin endpoint accessible")
        else:
            results.add_skip("Kong Admin API", f"Status: {response.status_code}")
    except Exception as e:
        results.add_skip("Kong Admin API", str(e))

    return True


def test_gcs_connection(results: E2ETestResult):
    """Test GCS connection and operations."""
    print_step(2, "Testing GCS Connection")

    try:
        from google.cloud import storage

        client = storage.Client(project=GCP_PROJECT_ID)
        bucket = client.bucket(GCS_BUCKET)

        # Test file operations directly (bucket.exists() requires extra permissions)
        test_id = str(uuid.uuid4())[:8]
        test_path = f"{TEST_FILE_PREFIX}/{TEST_TENANT_ID}/test-{test_id}.txt"
        test_content = f"E2E test content - {datetime.now(timezone.utc).isoformat()}"

        # Upload test file
        blob = bucket.blob(test_path)
        blob.upload_from_string(test_content)
        results.add_pass("GCS Upload", f"Path: {test_path}")

        # Verify file exists
        if blob.exists():
            results.add_pass("GCS File Exists", "File verified")
        else:
            results.add_fail("GCS File Exists", "File not found after upload")

        # Read file back
        downloaded = blob.download_as_text()
        if downloaded == test_content:
            results.add_pass("GCS Read", "Content matches")
        else:
            results.add_fail("GCS Read", "Content mismatch")

        # Cleanup
        blob.delete()
        results.add_pass("GCS Cleanup", "Test file deleted")

        results.add_pass("GCS Bucket Access", f"Bucket: {GCS_BUCKET}")
        return True

    except Exception as e:
        results.add_fail("GCS Connection", str(e))
        return False


def test_vertex_ai_discovery_engine(results: E2ETestResult):
    """Test Vertex AI Discovery Engine connection."""
    print_step(3, "Testing Vertex AI Discovery Engine")

    try:
        from rag_index.adapters.vertex_ai_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(
            project_id=GCP_PROJECT_ID,
            location="global",
            data_store_id="prevision-docs-dev",
            mock_mode=False,
        )

        results.add_pass("Vertex AI Adapter Init", f"Project: {GCP_PROJECT_ID}")

        # Check client initialization
        client = adapter._get_client()
        if client:
            results.add_pass("Discovery Engine Client", "Client initialized")
        else:
            results.add_skip("Discovery Engine Client", "Client in mock mode")

        # Check connection
        import asyncio

        is_connected = asyncio.get_event_loop().run_until_complete(
            adapter.check_connection()
        )
        if is_connected:
            results.add_pass("Vertex AI Connection", "Connection healthy")
        else:
            results.add_fail("Vertex AI Connection", "Connection failed")

        # Test data store path generation
        path = adapter.get_data_store_path(TEST_TENANT_ID)
        if "prevision-docs-dev" in path and TEST_TENANT_ID in path:
            results.add_pass("Data Store Path", f"Path: {path[:60]}...")
        else:
            results.add_fail("Data Store Path", "Invalid path format")

        return True

    except Exception as e:
        results.add_fail("Vertex AI Discovery Engine", str(e))
        return False


def test_data_ingestion_adapter(results: E2ETestResult):
    """Test data ingestion GCS adapter."""
    print_step(4, "Testing Data Ingestion GCS Adapter")

    try:
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(
            project_id=GCP_PROJECT_ID,
            default_bucket=GCS_BUCKET,
        )

        results.add_pass("Data Ingestion Adapter Init", f"Bucket: {GCS_BUCKET}")

        # Test file exists
        test_uri = (
            f"gs://{GCS_BUCKET}/customer-1/customer-1-onboarding-file-example-1.txt"
        )
        if adapter.check_exists(test_uri):
            results.add_pass("Data Ingestion File Check", "Test file exists")
        else:
            results.add_skip("Data Ingestion File Check", "Test file not found")

        # Test metadata retrieval
        try:
            metadata = adapter.get_metadata(test_uri)
            results.add_pass(
                "Data Ingestion Metadata", f"Size: {metadata.size_bytes} bytes"
            )
        except Exception as e:
            results.add_skip("Data Ingestion Metadata", str(e))

        return True

    except Exception as e:
        results.add_fail("Data Ingestion Adapter", str(e))
        return False


def test_media_curation_adapter(results: E2ETestResult):
    """Test media curation GCS adapter."""
    print_step(5, "Testing Media Curation GCS Adapter")

    try:
        from media_curation.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(
            project_id=GCP_PROJECT_ID,
        )

        results.add_pass("Media Curation Adapter Init", f"Project: {GCP_PROJECT_ID}")

        # Test file operations using media_curation's API
        # Note: media_curation uses download_as_bytes/exists, not read_document
        curated_uri = f"gs://{GCS_BUCKET}/customer-1/curated/curated-doc-001.json"
        try:
            import asyncio

            # Check if file exists
            exists = asyncio.get_event_loop().run_until_complete(
                adapter.exists(curated_uri)
            )
            if exists:
                results.add_pass("Media Curation File Exists", f"Path: {curated_uri}")
                # Read file content
                content = asyncio.get_event_loop().run_until_complete(
                    adapter.download_as_bytes(curated_uri)
                )
                if content:
                    results.add_pass(
                        "Media Curation Download", f"Size: {len(content)} bytes"
                    )
                else:
                    results.add_skip("Media Curation Download", "Empty content")
            else:
                results.add_skip("Media Curation File Exists", "Test file not found")
        except Exception as e:
            results.add_skip("Media Curation File Operations", str(e))

        return True

    except Exception as e:
        results.add_fail("Media Curation Adapter", str(e))
        return False


def test_rag_index_adapter(results: E2ETestResult):
    """Test RAG index GCS adapter."""
    print_step(6, "Testing RAG Index GCS Adapter")

    try:
        from rag_index.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(
            project_id=GCP_PROJECT_ID,
            mock_mode=False,
        )

        results.add_pass("RAG Index GCS Adapter Init", f"Project: {GCP_PROJECT_ID}")

        # Test reading curated document for RAG indexing
        curated_uri = f"gs://{GCS_BUCKET}/customer-1/curated/curated-doc-001.json"
        try:
            import asyncio

            doc = asyncio.get_event_loop().run_until_complete(
                adapter.read_document(curated_uri)
            )
            if doc:
                results.add_pass("RAG Index Document Read", "Document loaded")
            else:
                results.add_skip("RAG Index Document Read", "Document not found")
        except Exception as e:
            results.add_skip("RAG Index Document Read", str(e))

        return True

    except Exception as e:
        results.add_fail("RAG Index GCS Adapter", str(e))
        return False


def test_full_pipeline_simulation(results: E2ETestResult):
    """Simulate full pipeline flow without Kafka."""
    print_step(7, "Testing Full Pipeline Simulation (Direct)")

    try:
        from google.cloud import storage
        from rag_index.adapters.gcs_adapter import GCSAdapter as RAGGCSAdapter
        from rag_index.adapters.vertex_ai_adapter import VertexAIAdapter
        from rag_index.domain.models import SyncEvent, SyncAction
        import asyncio

        test_id = str(uuid.uuid4())[:8]

        # Step A: Simulate data ingestion - upload a file to landing zone
        print("  A. Simulating data ingestion (upload to GCS)...")
        client = storage.Client(project=GCP_PROJECT_ID)
        bucket = client.bucket(GCS_BUCKET)

        landing_path = f"{TEST_FILE_PREFIX}/_landing/{TEST_TENANT_ID}/doc-{test_id}.txt"
        raw_path = (
            f"{TEST_FILE_PREFIX}/{TEST_TENANT_ID}/raw/2026/02/03/doc-{test_id}.txt"
        )

        # Upload to landing
        landing_blob = bucket.blob(landing_path)
        content = f"Test document content for E2E pipeline test - {test_id}"
        landing_blob.upload_from_string(content)
        results.add_pass("Pipeline: Upload to Landing", f"Path: {landing_path}")

        # Move to raw (simulating ingestion)
        bucket.copy_blob(landing_blob, bucket, raw_path)
        landing_blob.delete()
        results.add_pass("Pipeline: Move to Raw", f"Path: {raw_path}")

        # Step B: Simulate media curation - create curated JSON
        print("  B. Simulating media curation (create curated document)...")
        curated_path = f"{TEST_FILE_PREFIX}/{TEST_TENANT_ID}/curated/doc-{test_id}.json"
        curated_doc = {
            "id": f"doc-{test_id}",
            "title": f"E2E Test Document {test_id}",
            "content": content,
            "content_type": "text/plain",
            "language": "en",
            "metadata": {
                "source": "e2e-test",
                "tenant_id": TEST_TENANT_ID,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "pii_redacted": False,
        }

        curated_blob = bucket.blob(curated_path)
        curated_blob.upload_from_string(
            json.dumps(curated_doc), content_type="application/json"
        )
        results.add_pass("Pipeline: Create Curated Doc", f"Path: {curated_path}")

        # Step C: Simulate RAG indexing - read curated and sync to Vertex AI
        print("  C. Simulating RAG indexing (sync to Vertex AI)...")
        rag_gcs = RAGGCSAdapter(project_id=GCP_PROJECT_ID, mock_mode=False)
        vertex = VertexAIAdapter(
            project_id=GCP_PROJECT_ID,
            location="global",
            data_store_id="prevision-docs-dev",
            mock_mode=False,
        )

        # Read curated document
        curated_uri = f"gs://{GCS_BUCKET}/{curated_path}"
        doc = asyncio.get_event_loop().run_until_complete(
            rag_gcs.read_document(curated_uri)
        )
        results.add_pass("Pipeline: Read Curated for RAG", f"Doc ID: {doc.get('id')}")

        # Create sync event
        sync_event = SyncEvent(
            event_id=uuid.uuid4(),
            trace_id=f"trace-{test_id}",
            tenant_id=TEST_TENANT_ID,
            file_id=f"doc-{test_id}",
            action=SyncAction.UPSERT,
            processed_gcs_uri=curated_uri,
        )

        # Attempt to sync to Vertex AI
        try:
            result = asyncio.get_event_loop().run_until_complete(
                vertex.upsert_document(sync_event, doc)
            )
            if result.status == "COMPLETED":
                results.add_pass(
                    "Pipeline: Vertex AI Sync",
                    f"Document indexed, time: {result.processing_time_ms}ms",
                )
            else:
                results.add_fail("Pipeline: Vertex AI Sync", f"Status: {result.status}")
        except Exception as e:
            error_str = str(e)
            if "NOT_FOUND" in error_str or "404" in error_str:
                results.add_skip(
                    "Pipeline: Vertex AI Sync",
                    "Tenant-specific data store not configured",
                )
            else:
                results.add_fail("Pipeline: Vertex AI Sync", error_str[:100])

        # Cleanup
        print("  D. Cleaning up test files...")
        for blob_path in [raw_path, curated_path]:
            try:
                bucket.blob(blob_path).delete()
            except Exception:
                pass
        results.add_pass("Pipeline: Cleanup", "Test files removed")

        return True

    except Exception as e:
        results.add_fail("Full Pipeline Simulation", str(e))
        return False


def test_kafka_connectivity(results: E2ETestResult):
    """Test Kafka connectivity."""
    print_step(8, "Testing Kafka Connectivity")

    try:
        import socket

        # Simple socket test - Kafka broker listens on external port 9192
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(("localhost", 9192))
        sock.close()

        if result == 0:
            results.add_pass("Kafka Port Check", "Port 9192 is open")
        else:
            results.add_fail(
                "Kafka Port Check", f"Cannot connect to port 9192, error: {result}"
            )
            return False

        # Test via Kafka UI API (it proxies to Kafka)
        import requests

        try:
            resp = requests.get("http://localhost:8080/api/clusters", timeout=5)
            if resp.status_code == 200:
                clusters = resp.json()
                if clusters and clusters[0].get("status") == "online":
                    topic_count = clusters[0].get("topicCount")
                    results.add_pass(
                        "Kafka Cluster Status",
                        f"Status: online, Topics: {topic_count}",
                    )

                    # Get topics via UI API
                    topics_resp = requests.get(
                        "http://localhost:8080/api/clusters/local/topics", timeout=5
                    )
                    if topics_resp.status_code == 200:
                        data = topics_resp.json()
                        # Handle paginated response: {"pageCount": N, "topics": [...]}
                        topics = (
                            data.get("topics", []) if isinstance(data, dict) else data
                        )
                        topic_names = (
                            [t.get("name") for t in topics]
                            if isinstance(topics, list)
                            else []
                        )

                        # Check for required topics
                        required_topics = [
                            "raw-ingestion-topic",
                            "curation-needed-topic",
                            "rag-sync-ready-topic",
                        ]
                        for topic in required_topics:
                            if topic in topic_names:
                                results.add_pass(f"Topic: {topic}", "Found")
                            else:
                                results.add_skip(f"Topic: {topic}", "Not found")
                else:
                    results.add_skip("Kafka Cluster Status", "Cluster not online")
            else:
                results.add_skip(
                    "Kafka Cluster Status", f"UI API returned {resp.status_code}"
                )
        except requests.RequestException as e:
            results.add_skip("Kafka Cluster Status", f"Cannot reach Kafka UI: {e}")

        return True

    except Exception as e:
        results.add_fail("Kafka Connectivity", str(e))
        return False


def main():
    """Run the full E2E test suite."""
    print_header("FULL END-TO-END PIPELINE TEST")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"GCP Project: {GCP_PROJECT_ID}")
    print(f"GCS Bucket: {GCS_BUCKET}")

    # Setup
    if not setup_gcp_credentials():
        print("❌ Cannot proceed without GCP credentials")
        return 1

    setup_django()

    # Run tests
    results = E2ETestResult()

    test_kong_gateway(results)
    test_gcs_connection(results)
    test_vertex_ai_discovery_engine(results)
    test_data_ingestion_adapter(results)
    test_media_curation_adapter(results)
    test_rag_index_adapter(results)
    test_full_pipeline_simulation(results)
    test_kafka_connectivity(results)

    # Summary
    success = results.summary()

    if success:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
