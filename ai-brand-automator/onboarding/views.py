import logging
import uuid
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Company, BrandAsset, OnboardingProgress
from .serializers import (
    CompanySerializer,
    BrandAssetSerializer,
    OnboardingProgressSerializer,
    CompanyCreateSerializer,
    CompanyUpdateSerializer,
    BrandAssetUploadSerializer,
)
from .services import get_pipeline_service
from files.services import gcs_service
from ai_services.services import ai_service
from brand_automator.validators import validate_file_upload, sanitize_filename

logger = logging.getLogger(__name__)


class CompanyViewSet(viewsets.ModelViewSet):
    """ViewSet for Company model"""

    queryset = Company.objects.select_related("tenant").all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup with optimized queries
        if hasattr(self.request, "tenant") and self.request.tenant:
            return Company.objects.filter(tenant=self.request.tenant).select_related(
                "tenant"
            )
        return Company.objects.select_related("tenant").all()

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return CompanyUpdateSerializer
        return CompanySerializer

    def perform_create(self, serializer):
        """
        Create company with proper tenant context.
        Each tenant gets exactly one company (OneToOneField).
        """
        # Get tenant from request (set by TenantMainMiddleware)
        tenant = getattr(self.request, "tenant", None)

        if not tenant:
            # MVP mode: If no tenant context, use public tenant
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(schema_name="public")
            except Tenant.DoesNotExist:
                raise ValueError(
                    "Public tenant not found. Ensure migrations have been run "
                    "and public tenant exists."
                )

        # Check if tenant already has a company (OneToOneField constraint)
        if Company.objects.filter(tenant=tenant).exists():
            raise ValueError(
                f"Tenant {tenant.name} already has a company. Cannot create another."
            )

        # Save company with tenant
        company = serializer.save(tenant=tenant)

        # Create onboarding progress
        OnboardingProgress.objects.create(
            tenant=tenant,
            company=company,
            current_step="company_info",
            completed_steps=["company_info"],
        )

        # Set up default pipeline configuration for this tenant
        pipeline_service = get_pipeline_service()
        pipeline_service.setup_tenant_pipeline_config(tenant.id)

    @action(detail=True, methods=["post"])
    def generate_brand_strategy(self, request, pk=None):
        """Generate AI-powered brand strategy"""
        company = self.get_object()

        # Prepare company data for AI service
        company_data = {
            "tenant": company.tenant,
            "name": company.name,
            "industry": company.industry,
            "target_audience": company.target_audience,
            "core_problem": company.core_problem,
            "brand_voice": company.brand_voice,
        }

        # Generate brand strategy using AI
        ai_result = ai_service.generate_brand_strategy(company_data)

        # Update company with AI-generated content
        company.vision_statement = ai_result["vision_statement"]
        company.mission_statement = ai_result["mission_statement"]
        company.values = ai_result["values"]
        company.positioning_statement = ai_result["positioning_statement"]
        company.save()

        serializer = self.get_serializer(company)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def generate_brand_identity(self, request, pk=None):
        """Generate AI-powered brand identity"""
        company = self.get_object()

        # Prepare company data for AI service
        company_data = {
            "tenant": company.tenant,
            "name": company.name,
            "industry": company.industry,
            "brand_voice": company.brand_voice,
            "target_audience": company.target_audience,
        }

        # Generate brand identity using AI
        ai_result = ai_service.generate_brand_identity(company_data)

        # Update company with AI-generated content
        company.color_palette_desc = ai_result["color_palette_desc"]
        company.font_recommendations = ai_result["font_recommendations"]
        company.messaging_guide = ai_result["messaging_guide"]
        company.save()

        serializer = self.get_serializer(company)
        return Response(serializer.data)


class BrandAssetViewSet(viewsets.ModelViewSet):
    """ViewSet for BrandAsset model"""

    queryset = BrandAsset.objects.select_related("tenant", "company").all()
    serializer_class = BrandAssetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup with optimized queries
        if hasattr(self.request, "tenant") and self.request.tenant:
            return BrandAsset.objects.filter(tenant=self.request.tenant).select_related(
                "tenant", "company"
            )
        return BrandAsset.objects.select_related("tenant", "company").all()

    @action(detail=False, methods=["post"])
    def upload(self, request):
        """Upload a brand asset file"""
        serializer = BrandAssetUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data["file"]
        file_type = serializer.validated_data["file_type"]

        # Define allowed file types
        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "video/mp4",
            "video/quicktime",
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        # Validate file
        validation_result = validate_file_upload(file, allowed_types, max_size_mb=50)
        if not validation_result["valid"]:
            return Response(
                {"error": validation_result["error"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sanitize filename
        safe_filename = sanitize_filename(file.name)

        # Get tenant from request (defensive access for MVP mode)
        tenant = getattr(request, "tenant", None)
        if not tenant:
            # MVP mode: If no tenant context, use public tenant
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(schema_name="public")
            except Tenant.DoesNotExist:
                raise ValueError(
                    "Public tenant not found. Ensure migrations have been run "
                    "and public tenant exists."
                )

        # Get company for the tenant
        company = get_object_or_404(Company, tenant=tenant)

        # Generate unique GCS path in _landing/ zone for pipeline processing
        # Format: _landing/{tenant_id}/{uuid}_{filename}
        unique_id = uuid.uuid4().hex[:8]
        landing_path = f"_landing/{tenant.id}/{unique_id}_{safe_filename}"

        # Upload to Google Cloud Storage
        gcs_uploaded = False
        try:
            if gcs_service.client and gcs_service.bucket:
                gcs_service.upload_file(file, landing_path, file.content_type)
                gcs_uploaded = True
            else:
                # GCS not configured - check if we should fail or allow for dev/testing
                require_gcs = getattr(settings, "REQUIRE_GCS_UPLOAD", False)
                if require_gcs:
                    logger.error("GCS is required but not configured")
                    return Response(
                        {"error": "File storage is not configured"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                logger.warning(
                    "GCS not configured, asset record will be created but file "
                    "is not stored. Set REQUIRE_GCS_UPLOAD=True in production."
                )
        except Exception as e:
            logger.error(f"GCS upload failed: {str(e)}")
            return Response(
                {"error": f"Failed to upload file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create asset record
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name=safe_filename,
            file_type=file_type,
            file_size=file.size,
            gcs_path=landing_path,
            processed=False,  # Will be set True after pipeline completes
            pipeline_status="pending" if gcs_uploaded else "failed",
            pipeline_error=""
            if gcs_uploaded
            else "GCS not configured - file not stored",
        )

        # Trigger data pipeline only if file was uploaded
        if gcs_uploaded:
            pipeline_service = get_pipeline_service()
            pipeline_service.publish_asset_event(asset)

        response_serializer = BrandAssetSerializer(asset)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def confirm_gcs_upload(self, request):
        """
        Confirm a direct GCS upload (when Kong uploads directly to GCS).

        This endpoint is called by the frontend after Kong successfully uploads
        a file directly to GCS, bypassing Django. It creates the BrandAsset
        record in the database to track the uploaded file.

        Request body:
        {
            "file_name": "original-filename.png",
            "file_type": "image",  # image, video, document, other
            "file_size": 1024,  # size in bytes
            "gcs_path": "assets/tenant-id/filename.png",
            "gcs_bucket": "brand-automator-assets",
            "company_id": 1  # optional, defaults to tenant's company
        }
        """
        # Get tenant from request (defensive access for MVP mode)
        tenant = getattr(request, "tenant", None)
        if not tenant:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(schema_name="public")
            except Tenant.DoesNotExist:
                return Response(
                    {"error": "Public tenant not found"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Validate required fields
        required_fields = ["file_name", "file_type", "file_size", "gcs_path"]
        for field in required_fields:
            if field not in request.data:
                return Response(
                    {"error": f"Missing required field: {field}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        file_name = request.data.get("file_name")
        file_type = request.data.get("file_type")
        file_size = request.data.get("file_size")
        gcs_path = request.data.get("gcs_path")
        gcs_bucket = request.data.get("gcs_bucket", "brand-automator-assets")
        company_id = request.data.get("company_id")

        # Validate file_type
        valid_file_types = ["image", "video", "document", "other"]
        if file_type not in valid_file_types:
            return Response(
                {"error": f"Invalid file_type. Must be one of: {valid_file_types}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file_size is positive integer
        try:
            file_size = int(file_size)
            if file_size <= 0:
                raise ValueError("File size must be positive")
        except (ValueError, TypeError):
            return Response(
                {"error": "file_size must be a positive integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get company for the tenant (or by company_id if provided)
        if company_id:
            company = get_object_or_404(Company, id=company_id, tenant=tenant)
        else:
            company = get_object_or_404(Company, tenant=tenant)

        # Sanitize filename
        safe_filename = sanitize_filename(file_name)

        # SECURITY: Validate and derive gcs_path server-side
        # Enforce tenant-scoped path pattern to prevent cross-tenant access
        # Accept both legacy assets/ path and new _landing/ path for pipeline
        assets_prefix = f"assets/{tenant.id}/"
        landing_prefix = f"_landing/{tenant.id}/"

        if not (
            gcs_path.startswith(assets_prefix) or gcs_path.startswith(landing_prefix)
        ):
            logger.warning(
                f"Invalid gcs_path '{gcs_path}' for tenant {tenant.id}. "
                f"Expected prefix: {assets_prefix} or {landing_prefix}"
            )
            return Response(
                {"error": "Invalid GCS path. Path must be within tenant scope."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify filename in path contains sanitized filename
        # (may have UUID prefix like {uuid}_{filename})
        path_filename = gcs_path.split("/")[-1] if "/" in gcs_path else gcs_path
        if not path_filename.endswith(safe_filename):
            logger.warning(
                f"GCS path filename '{path_filename}' doesn't contain "
                f"sanitized filename '{safe_filename}'"
            )
            return Response(
                {"error": "GCS path filename mismatch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create asset record for the direct GCS upload
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name=safe_filename,
            file_type=file_type,
            file_size=file_size,
            gcs_path=gcs_path,
            gcs_bucket=gcs_bucket,
            processed=False,  # Will be set True after pipeline completes
            pipeline_status="pending",
        )

        # Trigger data pipeline
        pipeline_service = get_pipeline_service()
        pipeline_service.publish_asset_event(asset)

        response_serializer = BrandAssetSerializer(asset)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def retry_pipeline(self, request, pk=None):
        """
        Retry pipeline processing for a failed asset.

        This endpoint allows retrying the data pipeline for assets that
        failed during processing.
        """
        asset = self.get_object()

        if asset.pipeline_status not in ("failed", "pending"):
            return Response(
                {
                    "error": (
                        f"Cannot retry asset with status '{asset.pipeline_status}'. "
                        "Only 'failed' or 'pending' assets can be retried."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        pipeline_service = get_pipeline_service()
        trace_id = pipeline_service.retry_asset_pipeline(asset)

        if trace_id:
            return Response(
                {
                    "status": "success",
                    "message": "Pipeline retry initiated",
                    "trace_id": trace_id,
                }
            )
        else:
            return Response(
                {"status": "error", "message": "Failed to retry pipeline"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def update_pipeline_status(self, request, pk=None):
        """
        Update pipeline status for an asset (webhook for pipeline services).

        This endpoint is called by the data pipeline services to update
        the processing status of an asset.

        Request body:
        {
            "status": "ingested|curated|indexed|failed",
            "error": "optional error message",
            "trace_id": "optional trace id for verification"
        }
        """
        asset = self.get_object()

        new_status = request.data.get("status")
        error = request.data.get("error", "")
        trace_id = request.data.get("trace_id")

        valid_statuses = ["pending", "ingested", "curated", "indexed", "failed"]
        if new_status not in valid_statuses:
            return Response(
                {"error": f"Invalid status. Must be one of: {valid_statuses}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optionally verify trace_id matches
        if trace_id and asset.pipeline_trace_id:
            if str(asset.pipeline_trace_id) != trace_id:
                logger.warning(
                    f"Trace ID mismatch for asset {asset.id}: "
                    f"expected {asset.pipeline_trace_id}, got {trace_id}"
                )

        # Update asset status
        asset.pipeline_status = new_status
        if error:
            asset.pipeline_error = error
        if new_status == "indexed":
            asset.processed = True

        asset.save(update_fields=["pipeline_status", "pipeline_error", "processed"])

        logger.info(
            f"Updated pipeline status for asset {asset.id} to {new_status}",
            extra={"asset_id": asset.id, "status": new_status, "trace_id": trace_id},
        )

        return Response({"status": "updated", "pipeline_status": new_status})


class OnboardingProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for OnboardingProgress model"""

    queryset = OnboardingProgress.objects.all()
    serializer_class = OnboardingProgressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup
        if hasattr(self.request, "tenant") and self.request.tenant:
            return OnboardingProgress.objects.filter(tenant=self.request.tenant)
        return OnboardingProgress.objects.all()

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current onboarding progress for the tenant"""
        # TODO: Get actual tenant from request in multi-tenant setup
        tenant = request.tenant
        progress = get_object_or_404(OnboardingProgress, tenant=tenant)
        serializer = self.get_serializer(progress)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def update_step(self, request):
        """Update current onboarding step"""
        step = request.data.get("step")
        completed = request.data.get("completed", False)

        if not step:
            return Response(
                {"error": "Step is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Get actual tenant from request in multi-tenant setup
        tenant = request.tenant
        progress = get_object_or_404(OnboardingProgress, tenant=tenant)

        progress.current_step = step
        if completed and step not in progress.completed_steps:
            progress.completed_steps.append(step)

        if step == "review":  # Final step
            progress.is_completed = True
            progress.completed_at = timezone.now()

        progress.save()

        serializer = self.get_serializer(progress)
        return Response(serializer.data)


# ============================================================================
# Webhook Endpoints (for internal pipeline services)
# ============================================================================


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def pipeline_status_webhook(request):
    """
    Webhook endpoint for data pipeline services to update asset status.

    This endpoint uses a shared secret for authentication instead of
    user JWT tokens, since it's called by internal services.

    Request body:
    {
        "asset_id": 123,
        "status": "ingested|curated|indexed|failed",
        "error": "optional error message",
        "trace_id": "trace UUID for verification",
        "secret": "shared secret for authentication"
    }

    Returns:
        200: Status updated successfully
        400: Invalid request data
        401: Invalid or missing secret
        404: Asset not found
    """
    # Validate shared secret - fail closed if not configured
    expected_secret = getattr(settings, "PIPELINE_WEBHOOK_SECRET", None)
    provided_secret = request.data.get("secret") or request.headers.get(
        "X-Pipeline-Secret"
    )

    if not expected_secret:
        logger.error("Pipeline webhook secret is not configured")
        return Response(
            {"error": "Webhook authentication is not configured"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if provided_secret != expected_secret:
        logger.warning("Pipeline webhook called with invalid secret")
        return Response(
            {"error": "Invalid or missing authentication"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Extract and validate request data
    asset_id = request.data.get("asset_id")
    new_status = request.data.get("status")
    error_message = request.data.get("error", "")
    trace_id = request.data.get("trace_id")

    if not asset_id:
        return Response(
            {"error": "asset_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_statuses = ["pending", "ingested", "curated", "indexed", "failed"]
    if new_status not in valid_statuses:
        return Response(
            {"error": f"Invalid status. Must be one of: {valid_statuses}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find and update the asset
    try:
        asset = BrandAsset.objects.get(id=asset_id)
    except BrandAsset.DoesNotExist:
        return Response(
            {"error": f"Asset {asset_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verify trace_id if provided
    if trace_id and asset.pipeline_trace_id:
        if str(asset.pipeline_trace_id) != trace_id:
            logger.warning(
                f"Trace ID mismatch for asset {asset_id}: "
                f"expected {asset.pipeline_trace_id}, got {trace_id}"
            )
            # Log warning but don't reject - trace_id mismatch might be from retry

    # Update asset status
    asset.pipeline_status = new_status
    if error_message:
        asset.pipeline_error = error_message
    else:
        # Clear any previous error when no error message is provided
        asset.pipeline_error = ""

    # Mark as processed when fully indexed
    if new_status == "indexed":
        asset.processed = True

    asset.save(update_fields=["pipeline_status", "pipeline_error", "processed"])

    logger.info(
        f"Pipeline webhook updated asset {asset_id} to {new_status}",
        extra={
            "asset_id": asset_id,
            "status": new_status,
            "trace_id": trace_id,
            "had_error": bool(error_message),
        },
    )

    return Response(
        {
            "status": "updated",
            "asset_id": asset_id,
            "pipeline_status": new_status,
        }
    )


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def pipeline_batch_status_webhook(request):
    """
    Webhook endpoint for batch status updates from pipeline services.

    This allows updating multiple assets in a single request, which is
    more efficient for the media_curation service that processes batches.

    Request body:
    {
        "updates": [
            {"asset_id": 123, "status": "curated", "trace_id": "..."},
            {"asset_id": 124, "status": "failed", "error": "..."}
        ],
        "secret": "shared secret for authentication"
    }

    Returns:
        200: Updates processed with summary
        401: Invalid or missing secret
    """
    # Validate shared secret - fail closed if not configured
    expected_secret = getattr(settings, "PIPELINE_WEBHOOK_SECRET", None)
    provided_secret = request.data.get("secret") or request.headers.get(
        "X-Pipeline-Secret"
    )

    if not expected_secret:
        logger.error("Pipeline batch webhook secret is not configured")
        return Response(
            {"error": "Webhook authentication is not configured"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if provided_secret != expected_secret:
        logger.warning("Pipeline batch webhook called with invalid secret")
        return Response(
            {"error": "Invalid or missing authentication"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    updates = request.data.get("updates", [])
    if not updates:
        return Response(
            {"error": "updates array is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = {"success": 0, "failed": 0, "errors": []}

    for update in updates:
        asset_id = update.get("asset_id")
        new_status = update.get("status")
        error_message = update.get("error", "")

        try:
            asset = BrandAsset.objects.get(id=asset_id)
            asset.pipeline_status = new_status
            if error_message:
                asset.pipeline_error = error_message
            else:
                # Clear any previous error when no error message is provided
                asset.pipeline_error = ""
            if new_status == "indexed":
                asset.processed = True
            asset.save(update_fields=["pipeline_status", "pipeline_error", "processed"])
            results["success"] += 1
        except BrandAsset.DoesNotExist:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id} not found")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id}: {str(e)}")

    logger.info(
        f"Pipeline batch webhook processed {len(updates)} updates",
        extra=results,
    )

    return Response(results)
