#!/usr/bin/env python3
"""
Setup Vertex AI Discovery Engine for zorven-503517.

This script:
1. Enables the Discovery Engine API
2. Creates a data store for document indexing
3. Verifies the setup

Run with:
    GOOGLE_APPLICATION_CREDENTIALS=credentials/gcs-credentials.json \
    python scripts/setup_vertex_ai_discovery_engine.py
"""

import os
import sys

# Ensure credentials are set
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    print("Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
    sys.exit(1)

PROJECT_ID = "zorven-503517"
LOCATION = "global"  # Use 'global' for Discovery Engine API endpoint
DATA_STORE_ID = "prevision-docs-dev"
DATA_STORE_DISPLAY_NAME = "Prevision Docs Dev"
GCS_URI = "gs://zorven-raw-assets/customer-1/curated/"


def enable_discovery_engine_api():
    """Enable the Discovery Engine API."""
    print("\n1. Enabling Discovery Engine API...")
    try:
        from google.cloud import service_usage_v1

        client = service_usage_v1.ServiceUsageClient()

        # Enable the API
        request = service_usage_v1.EnableServiceRequest(
            name=f"projects/{PROJECT_ID}/services/discoveryengine.googleapis.com"
        )

        operation = client.enable_service(request=request)
        result = operation.result()  # Wait for completion

        print(f"   ✅ Discovery Engine API enabled: {result.service.name}")
        return True

    except Exception as e:
        error_msg = str(e)
        if "already enabled" in error_msg.lower() or "ALREADY_EXISTS" in error_msg:
            print("   ✅ Discovery Engine API already enabled")
            return True
        elif "PERMISSION_DENIED" in error_msg:
            print(
                "   ⚠️  Permission denied. "
                "Service account needs 'Service Usage Admin' role."
            )
            print("      You can enable manually via GCP Console or run:")
            print(
                f"      gcloud services enable discoveryengine.googleapis.com "
                f"--project={PROJECT_ID}"
            )
            return False
        else:
            print(f"   ❌ Failed to enable API: {e}")
            return False


def check_discovery_engine_api():
    """Check if Discovery Engine API is enabled."""
    print("\n2. Checking Discovery Engine API status...")
    try:
        from google.cloud import service_usage_v1

        client = service_usage_v1.ServiceUsageClient()

        request = service_usage_v1.GetServiceRequest(
            name=f"projects/{PROJECT_ID}/services/discoveryengine.googleapis.com"
        )

        service = client.get_service(request=request)

        if service.state == service_usage_v1.State.ENABLED:
            print("   ✅ Discovery Engine API is ENABLED")
            return True
        else:
            print(f"   ❌ Discovery Engine API state: {service.state.name}")
            return False

    except Exception as e:
        print(f"   ⚠️  Could not check API status: {e}")
        return False


def list_existing_data_stores():
    """List existing data stores."""
    print("\n3. Checking existing data stores...")
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine

        client = discoveryengine.DataStoreServiceClient()

        parent = (
            f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection"
        )

        request = discoveryengine.ListDataStoresRequest(parent=parent)

        data_stores = list(client.list_data_stores(request=request))

        if data_stores:
            print(f"   Found {len(data_stores)} existing data store(s):")
            for ds in data_stores:
                print(f"      - {ds.display_name} ({ds.name})")
            return data_stores
        else:
            print("   No existing data stores found")
            return []

    except Exception as e:
        error_msg = str(e)
        if "API not enabled" in error_msg or "403" in error_msg:
            print("   ⚠️  Discovery Engine API not enabled or permission denied")
        else:
            print(f"   ⚠️  Could not list data stores: {e}")
        return []


def create_data_store():
    """Create a new data store for document indexing."""
    print(f"\n4. Creating data store: {DATA_STORE_ID}...")
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine

        client = discoveryengine.DataStoreServiceClient()

        parent = (
            f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection"
        )

        # Create unstructured data store for documents
        data_store = discoveryengine.DataStore(
            display_name=DATA_STORE_DISPLAY_NAME,
            industry_vertical=discoveryengine.IndustryVertical.GENERIC,
            solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
            content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
        )

        request = discoveryengine.CreateDataStoreRequest(
            parent=parent,
            data_store=data_store,
            data_store_id=DATA_STORE_ID,
        )

        operation = client.create_data_store(request=request)
        print("   ⏳ Data store creation in progress (this may take a few minutes)...")

        result = operation.result()  # Wait for completion

        print(f"   ✅ Data store created: {result.name}")
        return result

    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg:
            print(f"   ✅ Data store already exists: {DATA_STORE_ID}")
            return True
        elif "PERMISSION_DENIED" in error_msg:
            print(
                "   ❌ Permission denied. "
                "Service account needs 'Discovery Engine Admin' role."
            )
            print(f"      Run: gcloud projects add-iam-policy-binding {PROJECT_ID} \\")
            sa = f"zorven-service-account@{PROJECT_ID}.iam.gserviceaccount.com"
            print(f"             --member='serviceAccount:{sa}' \\")
            print("             --role='roles/discoveryengine.admin'")
            return False
        else:
            print(f"   ❌ Failed to create data store: {e}")
            return False


def verify_connection():
    """Verify the Discovery Engine connection."""
    print("\n5. Verifying Discovery Engine connection...")
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine

        # Try to create a client
        discoveryengine.DocumentServiceClient()

        print("   ✅ Discovery Engine client initialized successfully")
        print(f"   Project: {PROJECT_ID}")
        print(f"   Location: {LOCATION}")
        print(f"   Data Store ID: {DATA_STORE_ID}")
        return True

    except Exception as e:
        print(f"   ❌ Connection verification failed: {e}")
        return False


def print_env_settings():
    """Print the .env settings to add."""
    print("\n" + "=" * 60)
    print("Add these settings to your .env file:")
    print("=" * 60)
    print(
        f"""
# Vertex AI Discovery Engine Configuration
VERTEX_AI_PROJECT_ID={PROJECT_ID}
VERTEX_AI_LOCATION={LOCATION}
VERTEX_AI_DATA_STORE_ID={DATA_STORE_ID}
VERTEX_AI_MOCK_MODE=False
"""
    )


def main():
    print("=" * 60)
    print("Vertex AI Discovery Engine Setup for zorven-503517")
    print("=" * 60)

    # Step 1: Enable API
    api_enabled = enable_discovery_engine_api()

    # Step 2: Check API status
    if not api_enabled:
        api_enabled = check_discovery_engine_api()

    # Step 3: List existing data stores
    existing_stores = list_existing_data_stores()

    # Step 4: Create data store if needed
    store_exists = (
        any(DATA_STORE_ID in str(ds.name) for ds in existing_stores)
        if existing_stores
        else False
    )

    if not store_exists:
        create_data_store()
    else:
        print(f"\n4. Data store {DATA_STORE_ID} already exists, skipping creation")

    # Step 5: Verify connection
    verify_connection()

    # Print env settings
    print_env_settings()

    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("1. Add the .env settings shown above")
    print("2. Import documents to the data store via GCP Console or API")
    print("3. Run the integration tests")


if __name__ == "__main__":
    main()
