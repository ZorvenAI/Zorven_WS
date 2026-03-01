"""Internal service-to-service endpoints for asset registration.

These endpoints are authenticated via X-Service-Token (same pattern
as orchestrator callbacks) and are NOT exposed through Kong.

Used by rag-uploader-agent-service to register BrandAsset records
before emitting IngestionEvents to Kafka.
"""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import Tenant
from .models import Company, BrandAsset

logger = logging.getLogger(__name__)


def _verify_service_token(request):
    """Verify X-Service-Token header against configured secret.

    Returns None on success, or an error Response on failure.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "ORCHESTRATOR_SERVICE_TOKEN", "")
    if not expected or token != expected:
        return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
    return None


def _get_tenant_id(request):
    """Extract tenant ID from X-Tenant-ID header."""
    return request.META.get("HTTP_X_TENANT_ID", "")


def _mime_to_file_type(mime_type: str) -> str:
    """Map MIME type string to BrandAsset file_type category."""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    return "document"


class InternalAssetRegisterView(APIView):
    """Register a BrandAsset from an internal pipeline service.

    POST /api/v1/internal/assets/register/

    This endpoint:
    - Triggers the data pipeline via Celery (Kafka fallback) after registration
    - Does NOT validate GCS path format strictly
    - Uses X-Service-Token authentication (no JWT required)

    Request body:
    {
        "file_name": "report.pdf",
        "file_type": "application/pdf",  # MIME type
        "file_size": 1024,
        "gcs_uri": "gs://bucket/path/report.pdf"
    }

    Response (201):
    {
        "asset_id": 123,
        "company_id": 45,
        "file_name": "report.pdf",
        "pipeline_status": "pending"
    }
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        auth_error = _verify_service_token(request)
        if auth_error:
            return auth_error

        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response(
                {"error": "X-Tenant-ID header required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve tenant
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except (Tenant.DoesNotExist, ValueError):
            return Response(
                {"error": f"Tenant {tenant_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate required fields
        file_name = request.data.get("file_name")
        if not file_name:
            return Response(
                {"error": "file_name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mime_type = request.data.get("file_type", "application/octet-stream")
        gcs_uri = request.data.get("gcs_uri", "")

        # Validate file_size is a non-negative integer
        raw_file_size = request.data.get("file_size", 0)
        try:
            file_size = int(raw_file_size)
        except (TypeError, ValueError):
            return Response(
                {"error": "file_size must be a non-negative integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file_size < 0:
            return Response(
                {"error": "file_size must be a non-negative integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse GCS URI to extract bucket and path
        gcs_bucket = ""
        gcs_path = ""
        if gcs_uri.startswith("gs://"):
            parts = gcs_uri[5:].split("/", 1)
            gcs_bucket = parts[0]
            gcs_path = parts[1] if len(parts) > 1 else ""

        # Map MIME type to BrandAsset file_type category
        asset_file_type = _mime_to_file_type(mime_type)

        # Get company for tenant (defaults to first company)
        company = Company.objects.filter(tenant=tenant).first()
        if not company:
            return Response(
                {"error": "No company found for this tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Atomic upsert to avoid race conditions
        asset, created = BrandAsset.objects.update_or_create(
            tenant=tenant,
            company=company,
            file_name=file_name,
            defaults={
                "file_type": asset_file_type,
                "file_size": file_size,
                "gcs_path": gcs_path,
                "gcs_bucket": gcs_bucket,
                "pipeline_status": "pending",
                "pipeline_error": "",
            },
        )
        logger.info(
            "%s asset %s for pipeline registration: '%s'",
            "Created" if created else "Updated",
            asset.id,
            file_name,
        )

        # Trigger the data pipeline (ingestion → curation → indexing)
        # Uses Celery sync pipeline when Kafka is disabled
        pipeline_status = asset.pipeline_status
        if gcs_uri.startswith("gs://"):
            try:
                from onboarding.services import get_pipeline_service

                pipeline_service = get_pipeline_service()
                pipeline_service.publish_asset_event(asset)
                asset.refresh_from_db()
                pipeline_status = asset.pipeline_status
                logger.info(
                    "Pipeline triggered for asset %s (status=%s)",
                    asset.id,
                    pipeline_status,
                )
            except Exception as e:
                logger.warning(
                    "Pipeline dispatch failed for asset %s: %s",
                    asset.id,
                    e,
                )

        return Response(
            {
                "asset_id": asset.id,
                "company_id": company.id,
                "file_name": asset.file_name,
                "pipeline_status": pipeline_status,
            },
            status=status.HTTP_201_CREATED,
        )
