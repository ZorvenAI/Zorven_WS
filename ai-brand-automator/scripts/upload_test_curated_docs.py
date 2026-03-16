#!/usr/bin/env python3
"""
Upload sample curated JSON documents for RAG index testing.

Run with:
    GOOGLE_APPLICATION_CREDENTIALS=credentials/gcs-credentials.json \\
        python scripts/upload_test_curated_docs.py
"""

import json
from datetime import datetime, timezone

from google.cloud import storage


def main():
    """Upload sample curated documents to test bucket."""
    client = storage.Client(project="brandsol-project")
    bucket = client.bucket("onboarding-brandsol-customer-bucket-1")

    # Sample curated document 1 - Standard document
    doc1 = {
        "id": "curated-doc-001",
        "title": "Brand Strategy Overview",
        "content": (
            "This document outlines the key elements of brand strategy "
            "including positioning, messaging, and visual identity "
            "guidelines for the Zorven AI platform."
        ),
        "metadata": {
            "author": "AI Curator",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_type": "text/plain",
            "source_file": "customer-1-onboarding-file-example-1.txt",
            "tenant_id": "customer-1",
            "language": "en",
        },
        "extracted_entities": ["brand strategy", "positioning", "visual identity"],
        "summary": "Overview of brand strategy fundamentals.",
    }

    blob1 = bucket.blob("customer-1/curated/curated-doc-001.json")
    blob1.upload_from_string(
        json.dumps(doc1, indent=2), content_type="application/json"
    )
    print(f"Uploaded: gs://{bucket.name}/{blob1.name}")

    # Sample curated document 2 - With PII redacted
    doc2 = {
        "id": "curated-doc-002",
        "title": "Customer Onboarding Data",
        "content": (
            "Customer contact information: [EMAIL_REDACTED] "
            "Phone: [PHONE_REDACTED]. Preferred communication: email."
        ),
        "metadata": {
            "author": "AI Curator",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_type": "application/pdf",
            "source_file": "Kannada-alphabets.pdf",
            "tenant_id": "customer-1",
            "pii_redacted": True,
        },
        "page_count": 5,
    }

    blob2 = bucket.blob("customer-1/curated/curated-doc-002.json")
    blob2.upload_from_string(
        json.dumps(doc2, indent=2), content_type="application/json"
    )
    print(f"Uploaded: gs://{bucket.name}/{blob2.name}")

    # Sample curated document 3 - Media transcription
    doc3 = {
        "id": "curated-doc-003",
        "title": "Video Transcription - Test Video",
        "content": (
            "This is a sample video transcription. The video discusses "
            "product features and demonstrates key functionality."
        ),
        "metadata": {
            "author": "AI Curator",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_type": "video/mp4",
            "source_file": "Test-video.mp4",
            "tenant_id": "customer-1",
            "duration_seconds": 120,
        },
        "summary": "Product demo video transcription.",
    }

    blob3 = bucket.blob("customer-1/curated/curated-doc-003.json")
    blob3.upload_from_string(
        json.dumps(doc3, indent=2), content_type="application/json"
    )
    print(f"Uploaded: gs://{bucket.name}/{blob3.name}")

    print("\n✅ All sample curated documents uploaded successfully!")


if __name__ == "__main__":
    main()
