import logging
import uuid
import math
from urllib.parse import urlencode
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Count, Q
from django.db import IntegrityError
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
from tenants.permissions import (
    RoleBasedPermissionMixin,
    IsTenantViewer,
    IsTenantEditor,
    IsTenantAdmin,
)

logger = logging.getLogger(__name__)


class CompanyViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for Company model.

    Permissions:
        - list, retrieve: IsTenantViewer (any member)
        - create, update, partial_update, destroy: IsTenantAdmin
        - generate_brand_strategy, generate_brand_identity: IsTenantEditor
    """

    queryset = Company.objects.select_related("tenant").all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantAdmin],
        "update": [IsAuthenticated, IsTenantAdmin],
        "partial_update": [IsAuthenticated, IsTenantAdmin],
        "destroy": [IsAuthenticated, IsTenantAdmin],
        "generate_brand_strategy": [IsAuthenticated, IsTenantEditor],
        "generate_brand_identity": [IsAuthenticated, IsTenantEditor],
        "generate_onboarding_pdf": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup with optimized queries
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            return Company.objects.filter(tenant=tenant).select_related("tenant")
        return Company.objects.select_related("tenant").none()

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
        # Get tenant from request (set by JWTTenantMiddleware)
        tenant = getattr(self.request, "tenant", None)

        if not tenant:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "No tenant context. Please log in again to obtain "
                "a valid tenant-scoped token."
            )

        # Check if tenant already has a company (OneToOneField constraint)
        if Company.objects.filter(tenant=tenant).exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {
                    "error": "duplicate_company",
                    "message": (
                        f"Tenant {tenant.name} already has a company. "
                        "Use PATCH to update instead of POST to create."
                    ),
                }
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

    @action(detail=True, methods=["post"])
    def generate_onboarding_pdf(self, request, pk=None):
        """Generate a PDF summary of all onboarding data and store it
        in the RAG knowledge base via the data processing pipeline.

        Creates an ``onboarding_data.pdf`` file containing every field
        collected during the onboarding steps, uploads it to GCS, creates
        a BrandAsset record, and triggers the ingestion pipeline so the
        document is indexed alongside other uploaded brand assets.
        """
        company = self.get_object()
        tenant = getattr(request, "tenant", None)

        if not tenant:
            return Response(
                {"error": "No tenant context. Please log in again."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # --- Build the PDF with fpdf2 ---
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 12, "Brand Onboarding Summary", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        def _sanitize(text):
            """Replace Unicode characters unsupported by Helvetica."""
            replacements = {
                "\u2018": "'",
                "\u2019": "'",  # curly single quotes
                "\u201c": '"',
                "\u201d": '"',  # curly double quotes
                "\u2013": "-",
                "\u2014": "--",  # en-dash, em-dash
                "\u2026": "...",  # ellipsis
                "\u00a0": " ",  # non-breaking space
                "\u2022": "-",  # bullet
            }
            for orig, repl in replacements.items():
                text = text.replace(orig, repl)
            # Strip any remaining non-latin1 characters as a safety net
            return text.encode("latin-1", errors="replace").decode("latin-1")

        def _section(title):
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(60, 60, 180)
            pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

        def _wrap_text(text, max_token_length=60):
            """Sanitize text and break very long tokens to avoid layout errors.

            Args:
                text: Original text value.
                max_token_length: Maximum length for any single token.

            Returns:
                A sanitized text string where long tokens are split into
                smaller chunks separated by spaces, so fpdf2.multi_cell
                can wrap them safely.
            """
            sanitized = _sanitize(text or "")
            tokens = sanitized.split(" ")
            wrapped_tokens = []
            for token in tokens:
                if len(token) > max_token_length:
                    for i in range(0, len(token), max_token_length):
                        wrapped_tokens.append(token[i : i + max_token_length])
                else:
                    wrapped_tokens.append(token)
            return " ".join(wrapped_tokens)

        def _field(label, value):
            if not value:
                return
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, f"{label}:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            # Wrap and sanitize text so multi_cell doesn't see long
            # unbreakable tokens (e.g., very long URLs).
            pdf.multi_cell(0, 5, _wrap_text(str(value)))
            pdf.ln(2)

        # Company Information
        _section("Company Information")
        _field("Company Name", company.name)
        _field("Industry", company.industry)
        _field("Description", company.description)
        _field("Core Problem", company.core_problem)
        _field("Website", company.website)
        _field("Physical Address", company.formatted_address)

        # Target Audience
        _section("Target Audience")
        _field("Primary Audience", company.target_audience)
        _field("Demographics", company.demographics)
        _field("Psychographics", company.psychographics)
        _field("Pain Points", company.pain_points)
        _field("Desired Outcomes", company.desired_outcomes)

        # Brand Details
        _section("Brand Details")
        _field("Brand Voice", company.brand_voice)
        _field("Vision Statement", company.vision_statement)
        _field("Mission Statement", company.mission_statement)
        _field("Core Values", company.values)
        _field("Positioning Statement", company.positioning_statement)
        _field("Tagline", company.tagline)
        _field("Value Proposition", company.value_proposition)
        _field("Elevator Pitch", company.elevator_pitch)

        # Brand Identity
        if (
            company.color_palette_desc
            or company.font_recommendations
            or company.messaging_guide
        ):
            _section("Brand Identity")
            _field("Color Palette", company.color_palette_desc)
            _field("Font Recommendations", company.font_recommendations)
            _field("Messaging Guide", company.messaging_guide)

        raw_pdf = pdf.output()
        if isinstance(raw_pdf, bytearray):
            pdf_bytes = bytes(raw_pdf)
        elif isinstance(raw_pdf, str):
            # fpdf2 historically uses Latin-1-compatible output
            pdf_bytes = raw_pdf.encode("latin1")
        else:
            pdf_bytes = raw_pdf

        # --- Upload to GCS and create BrandAsset ---
        safe_filename = "onboarding_data.pdf"
        unique_id = uuid.uuid4().hex[:8]
        landing_path = f"_landing/{tenant.id}/{unique_id}_{safe_filename}"

        raw_bucket = tenant.get_raw_bucket() if tenant else gcs_service.bucket_name

        gcs_uploaded = False
        try:
            target_bucket = gcs_service.get_bucket(raw_bucket)
            if target_bucket:
                from django.core.files.uploadedfile import SimpleUploadedFile

                pdf_file = SimpleUploadedFile(
                    safe_filename, pdf_bytes, content_type="application/pdf"
                )
                gcs_service.upload_file(
                    pdf_file,
                    landing_path,
                    "application/pdf",
                    bucket_name=raw_bucket,
                )
                gcs_uploaded = True
            else:
                if not settings.DEBUG:
                    logger.error(
                        "GCS_CREDENTIALS_JSON not configured — cannot store "
                        "onboarding PDF. Set the env var on Railway."
                    )
                else:
                    logger.warning(
                        "GCS not configured (DEBUG mode) — onboarding PDF "
                        "not stored."
                    )
        except Exception as e:
            logger.exception(
                "GCS upload failed for onboarding PDF (bucket=%s)", raw_bucket
            )
            return Response(
                {"error": f"Failed to store onboarding PDF: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Upsert: replace existing onboarding_data.pdf asset if present
        existing_asset = BrandAsset.objects.filter(
            tenant=tenant, company=company, file_name=safe_filename
        ).first()

        if existing_asset:
            existing_asset.file_size = len(pdf_bytes)
            existing_asset.gcs_path = landing_path
            existing_asset.gcs_bucket = raw_bucket
            existing_asset.processed = False
            existing_asset.pipeline_status = "pending" if gcs_uploaded else "failed"
            existing_asset.pipeline_error = (
                "" if gcs_uploaded else "GCS not configured - file not stored"
            )
            existing_asset.pipeline_trace_id = None
            existing_asset.uploaded_at = timezone.now()
            existing_asset.save()
            asset = existing_asset
        else:
            asset = BrandAsset.objects.create(
                tenant=tenant,
                company=company,
                file_name=safe_filename,
                file_type="document",
                file_size=len(pdf_bytes),
                gcs_path=landing_path,
                gcs_bucket=raw_bucket,
                processed=False,
                pipeline_status=("pending" if gcs_uploaded else "failed"),
                pipeline_error=(
                    "" if gcs_uploaded else "GCS not configured - file not stored"
                ),
            )

        # Trigger the data-ingestion pipeline
        if gcs_uploaded:
            pipeline_service = get_pipeline_service()
            pipeline_service.publish_asset_event(asset)

        if gcs_uploaded:
            message = "Onboarding PDF generated and queued for RAG indexing."
            response_status = status.HTTP_201_CREATED
        else:
            message = (
                "Onboarding PDF generated but not uploaded or queued for RAG "
                "indexing: GCS not configured - file not stored."
            )
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(
            {
                "message": message,
                "asset": BrandAssetSerializer(asset).data,
            },
            status=response_status,
        )


class BrandAssetViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for BrandAsset model.

    Permissions:
        - list, retrieve, signed_url, status: IsTenantViewer
        - upload, create, update, destroy, confirm_gcs_upload,
          retry_pipeline, update_pipeline_status: IsTenantEditor
    """

    queryset = BrandAsset.objects.select_related("tenant", "company").all()
    serializer_class = BrandAssetSerializer
    permission_classes = [IsAuthenticated]
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "signed_url": [IsAuthenticated, IsTenantViewer],
        "status": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "update": [IsAuthenticated, IsTenantEditor],
        "partial_update": [IsAuthenticated, IsTenantEditor],
        "destroy": [IsAuthenticated, IsTenantEditor],
        "upload": [IsAuthenticated, IsTenantEditor],
        "confirm_gcs_upload": [IsAuthenticated, IsTenantEditor],
        "retry_pipeline": [IsAuthenticated, IsTenantEditor],
        "update_pipeline_status": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup with optimized queries
        tenant = getattr(self.request, "tenant", None)
        logger.info(
            f"BrandAsset get_queryset: request.tenant={tenant}, "
            f"type={type(tenant)}, has_tenant={hasattr(self.request, 'tenant')}"
        )
        if tenant:
            qs = BrandAsset.objects.filter(tenant=tenant).select_related(
                "tenant", "company"
            )
            logger.info(
                f"BrandAsset get_queryset: filtered queryset count={qs.count()}"
            )
            return qs
        qs = BrandAsset.objects.select_related("tenant", "company").none()
        logger.info(f"BrandAsset get_queryset: unfiltered queryset count={qs.count()}")
        return qs

    def perform_create(self, serializer):
        """Attach active tenant on asset creation."""
        tenant = getattr(self.request, "tenant", None)
        serializer.save(tenant=tenant)

    def destroy(self, request, *args, **kwargs):
        """Delete asset and clean up associated files from GCS."""
        instance = self.get_object()

        # Try to delete file from GCS if it exists
        if instance.gcs_path:
            try:
                bucket = None

                # Prefer the asset-specific bucket if available
                gcs_client = getattr(gcs_service, "client", None)
                bucket_name = getattr(gcs_service, "bucket_name", None)

                if gcs_client and getattr(instance, "gcs_bucket", None):
                    bucket = gcs_client.bucket(instance.gcs_bucket)
                elif gcs_client and bucket_name:
                    bucket = gcs_client.bucket(bucket_name)
                else:
                    # Fallback to existing bucket attribute for backward compatibility
                    bucket = getattr(gcs_service, "bucket", None)

                if bucket:
                    blob = bucket.blob(instance.gcs_path)
                    if blob.exists():
                        blob.delete()
                        logger.info(f"Deleted GCS file: {instance.gcs_path}")
            except Exception as e:
                # Log but don't fail - still delete the DB record
                logger.warning(
                    f"Failed to delete GCS file for asset {instance.id}: {e}"
                )

        # Perform the standard delete
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """
        List assets with enhanced filtering, sorting, and pagination.

        Query parameters:
        - page: Page number (1-indexed, default: 1)
        - page_size: Items per page (default: 10, max: 50)
        - limit: Quick limit for onboarding view (3, 6, 9) - bypasses pagination
        - search: Search by filename (case-insensitive)
        - file_type: Filter by type (image, video, document, other)
        - status: Filter by pipeline status (pending, indexed, failed, etc.)
        - sort_by: Sort field (uploaded_at, file_name, file_size)
        - sort_order: Sort direction (asc, desc - default: desc)
        """
        queryset = self.get_queryset()

        # Extract query parameters
        search = request.query_params.get("search", "").strip()
        file_type = request.query_params.get("file_type", "").strip()
        status_filter = request.query_params.get("status", "").strip()
        sort_by = request.query_params.get("sort_by", "uploaded_at").strip()
        sort_order = request.query_params.get("sort_order", "desc").strip()
        limit = request.query_params.get("limit")
        page = request.query_params.get("page", "1")
        page_size = request.query_params.get("page_size", "10")

        # Apply search filter
        if search:
            queryset = queryset.filter(file_name__icontains=search)

        # Apply file type filter
        valid_file_types = ["image", "video", "document", "other"]
        if file_type and file_type in valid_file_types:
            queryset = queryset.filter(file_type=file_type)

        # Apply status filter
        valid_statuses = ["pending", "ingested", "curated", "indexed", "failed"]
        if status_filter and status_filter in valid_statuses:
            queryset = queryset.filter(pipeline_status=status_filter)

        # Apply sorting
        valid_sort_fields = ["uploaded_at", "file_name", "file_size"]
        if sort_by not in valid_sort_fields:
            sort_by = "uploaded_at"
        if sort_order not in ["asc", "desc"]:
            sort_order = "desc"

        order_prefix = "" if sort_order == "asc" else "-"
        queryset = queryset.order_by(f"{order_prefix}{sort_by}")

        total_count = queryset.count()

        # Handle quick limit mode (for onboarding compact view)
        if limit:
            try:
                limit_int = int(limit)
                if limit_int in [3, 6, 9]:
                    limited_queryset = queryset[:limit_int]
                    serializer = self.get_serializer(limited_queryset, many=True)
                    return Response(
                        {
                            "count": total_count,
                            "showing": min(limit_int, total_count),
                            "has_more": total_count > limit_int,
                            "results": serializer.data,
                            "filters_applied": {
                                "search": search or None,
                                "file_type": file_type or None,
                                "status": status_filter or None,
                                "sort_by": sort_by,
                                "sort_order": sort_order,
                            },
                        }
                    )
            except ValueError:
                # Invalid limit value - fall through to pagination mode
                pass

        # Handle pagination mode (for full file browser)
        try:
            page_int = max(1, int(page))
            page_size_int = min(50, max(1, int(page_size)))  # Cap at 50
        except ValueError:
            page_int = 1
            page_size_int = 10

        total_pages = math.ceil(total_count / page_size_int) if total_count > 0 else 1
        start_index = (page_int - 1) * page_size_int
        end_index = start_index + page_size_int

        paginated_queryset = queryset[start_index:end_index]
        serializer = self.get_serializer(paginated_queryset, many=True)

        # Build pagination URLs using proper URL encoding
        base_url = request.build_absolute_uri(request.path)
        query_params = request.query_params.copy()

        next_url = None
        if page_int < total_pages:
            query_params["page"] = str(page_int + 1)
            next_url = f"{base_url}?{urlencode(query_params)}"

        prev_url = None
        if page_int > 1:
            query_params["page"] = str(page_int - 1)
            prev_url = f"{base_url}?{urlencode(query_params)}"

        return Response(
            {
                "count": total_count,
                "total_pages": total_pages,
                "current_page": page_int,
                "page_size": page_size_int,
                "has_next": page_int < total_pages,
                "has_previous": page_int > 1,
                "next": next_url,
                "previous": prev_url,
                "results": serializer.data,
                "filters_applied": {
                    "search": search or None,
                    "file_type": file_type or None,
                    "status": status_filter or None,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                },
            }
        )

    @action(detail=True, methods=["get"], url_path="signed-url")
    def signed_url(self, request, pk=None):
        """
        Generate signed URLs for viewing/downloading a file.

        Returns temporary URLs that expire in 15 minutes.

        Query parameters:
        - download: If "true", returns URL with download disposition

        Response:
        {
            "view_url": "https://storage.googleapis.com/...",
            "download_url": "https://storage.googleapis.com/...",
            "expires_at": "2026-02-05T12:30:00Z"
        }
        """
        tenant = getattr(request, "tenant", None)
        logger.info(
            f"signed_url action called: pk={pk}, user={request.user}, "
            f"tenant={tenant}"
        )
        try:
            asset = self.get_object()
            logger.info(f"signed_url: got asset id={asset.id}")
        except Exception as e:
            logger.error(f"signed_url: get_object failed: {e}")
            raise

        if not asset.gcs_path:
            return Response(
                {"error": "Asset has no associated file"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expiry_minutes = getattr(settings, "GCS_SIGNED_URL_EXPIRY_MINUTES", 15)

        try:
            logger.info(f"signed_url: generating URL for gcs_path={asset.gcs_path}")
            # Generate view URL (inline display)
            view_result = gcs_service.generate_signed_url(
                file_path=asset.gcs_path,
                expiration_minutes=expiry_minutes,
                for_download=False,
                bucket_name=asset.gcs_bucket,
            )
            logger.info(f"signed_url: view_result={view_result}")

            # Generate download URL (attachment disposition)
            download_result = gcs_service.generate_signed_url(
                file_path=asset.gcs_path,
                expiration_minutes=expiry_minutes,
                for_download=True,
                filename=asset.file_name,
                bucket_name=asset.gcs_bucket,
            )
            logger.info(f"signed_url: download_result={download_result}")

            return Response(
                {
                    "view_url": view_result["url"],
                    "download_url": download_result["url"],
                    "expires_at": view_result["expires_at"],
                    "file_name": asset.file_name,
                    "file_type": asset.file_type,
                    "file_size": asset.file_size,
                }
            )

        except FileNotFoundError as e:
            logger.error(f"signed_url: FileNotFoundError: {e}")
            return Response(
                {"error": "File not found in storage"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(
                f"Failed to generate signed URL for asset {pk}: {e}", exc_info=True
            )
            return Response(
                {"error": "Failed to generate signed URL"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"])
    def status(self, request):
        """
        Get assets with their pipeline statuses.

        Query parameters:
        - pipeline_status: Filter by status (pending, ingested, curated,
          indexed, failed)
        - include_processed: Include fully processed assets (default: true)

        Returns list of assets with pipeline status information.
        """
        queryset = self.get_queryset()

        # Filter by pipeline_status if provided
        pipeline_status = request.query_params.get("pipeline_status")
        if pipeline_status:
            valid_statuses = ["pending", "ingested", "curated", "indexed", "failed"]
            if pipeline_status in valid_statuses:
                queryset = queryset.filter(pipeline_status=pipeline_status)

        # Option to exclude processed assets (useful for monitoring pending items)
        include_processed = request.query_params.get("include_processed", "true")
        if include_processed.lower() == "false":
            queryset = queryset.exclude(pipeline_status="indexed")

        # Order by upload date (most recent first)
        queryset = queryset.order_by("-uploaded_at")

        # Single query to get all counts (more efficient than 4 separate COUNT queries)
        counts = queryset.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(pipeline_status="pending")),
            failed=Count("id", filter=Q(pipeline_status="failed")),
            indexed=Count("id", filter=Q(pipeline_status="indexed")),
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "count": counts["total"],
                "results": serializer.data,
                "pending_count": counts["pending"],
                "failed_count": counts["failed"],
                "indexed_count": counts["indexed"],
            }
        )

    @action(detail=False, methods=["post"])
    def upload(self, request):
        """Upload a brand asset file"""
        serializer = BrandAssetUploadSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Asset upload validation failed: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data["file"]
        file_type = serializer.validated_data["file_type"]

        # Centralized allowed types from brand_automator.validators
        # (single source of truth for serializer, view, and validator)
        from brand_automator.validators import ALLOWED_UPLOAD_TYPES

        allowed_types = ALLOWED_UPLOAD_TYPES

        # Validate file
        validation_result = validate_file_upload(file, allowed_types, max_size_mb=50)
        if not validation_result["valid"]:
            logger.warning(
                "Asset upload file validation failed: file=%s content_type=%s "
                "size=%s error=%s",
                file.name,
                file.content_type,
                file.size,
                validation_result["error"],
            )
            return Response(
                {"error": validation_result["error"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sanitize filename
        safe_filename = sanitize_filename(file.name)

        # Get tenant from request (set by JWTTenantMiddleware)
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return Response(
                {"error": "No tenant context. Please log in again."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get company for the tenant
        company = Company.objects.filter(tenant=tenant).first()
        if not company:
            return Response(
                {
                    "error": "no_company",
                    "message": (
                        "No company found for this workspace. "
                        "Please complete onboarding first."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for duplicate file (same tenant + company + filename)
        raw_replace = request.data.get("replace_existing", "")
        if isinstance(raw_replace, bool):
            replace_existing = raw_replace
        else:
            replace_existing = str(raw_replace).lower() in ("true", "1")
        existing_asset = BrandAsset.objects.filter(
            tenant=tenant, company=company, file_name=safe_filename
        ).first()

        if existing_asset and not replace_existing:
            # Return 409 Conflict with existing asset info
            logger.info(
                f"Duplicate upload blocked: '{safe_filename}' already exists "
                f"as asset {existing_asset.id} for tenant {tenant.id}"
            )
            return Response(
                {
                    "error": "duplicate_file",
                    "message": f"A file named '{safe_filename}' already exists.",
                    "existing_asset": {
                        "id": existing_asset.id,
                        "file_name": existing_asset.file_name,
                        "file_size": existing_asset.file_size,
                        "uploaded_at": existing_asset.uploaded_at.isoformat(),
                        "pipeline_status": existing_asset.pipeline_status,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Generate unique GCS path in _landing/ zone for pipeline processing
        # Format: _landing/{tenant_id}/{uuid}_{filename}
        unique_id = uuid.uuid4().hex[:8]
        landing_path = f"_landing/{tenant.id}/{unique_id}_{safe_filename}"

        # Upload to Google Cloud Storage
        # Resolve the tenant-specific bucket (falls back to shared default)
        raw_bucket = tenant.get_raw_bucket() if tenant else gcs_service.bucket_name
        gcs_uploaded = False
        try:
            target_bucket = gcs_service.get_bucket(raw_bucket)
            if target_bucket:
                gcs_service.upload_file(
                    file, landing_path, file.content_type, bucket_name=raw_bucket
                )
                gcs_uploaded = True
            else:
                # GCS client is None — credentials not configured
                if not settings.DEBUG:
                    # Production: fail clearly so the operator fixes env vars
                    logger.error(
                        "GCS_CREDENTIALS_JSON not configured — cannot upload "
                        "files. Set the GCS_CREDENTIALS_JSON environment "
                        "variable with the service account JSON."
                    )
                    return Response(
                        {
                            "error": (
                                "File storage is not configured. Please contact "
                                "your administrator to set up GCS credentials."
                            )
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                logger.warning(
                    "GCS not configured (DEBUG mode), asset record will be "
                    "created but file is not stored."
                )
        except Exception as e:
            logger.exception(
                "GCS upload failed for %s (bucket=%s)",
                safe_filename,
                raw_bucket,
            )
            return Response(
                {
                    "error": (
                        f"Failed to upload file to storage: {e}. "
                        "Please try again or contact your administrator."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Handle replacement of existing asset
        actual_bucket = raw_bucket

        if existing_asset and replace_existing:
            # Delete old GCS blob (best-effort)
            old_gcs_path = existing_asset.gcs_path
            if old_gcs_path:
                try:
                    gcs_client = getattr(gcs_service, "client", None)
                    if gcs_client:
                        old_bucket = gcs_client.bucket(
                            existing_asset.gcs_bucket or actual_bucket
                        )
                        old_blob = old_bucket.blob(old_gcs_path)
                        if old_blob.exists():
                            old_blob.delete()
                            logger.info(
                                f"Deleted old GCS file during replacement: "
                                f"{old_gcs_path}"
                            )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete old GCS file '{old_gcs_path}' "
                        f"during replacement: {e}"
                    )

            # Update existing record instead of creating new one
            existing_asset.file_type = file_type
            existing_asset.file_size = file.size
            existing_asset.gcs_path = landing_path
            existing_asset.gcs_bucket = actual_bucket
            existing_asset.processed = False
            existing_asset.pipeline_status = "pending" if gcs_uploaded else "failed"
            existing_asset.pipeline_error = (
                "" if gcs_uploaded else "GCS not configured - file not stored"
            )
            existing_asset.pipeline_trace_id = None
            existing_asset.uploaded_at = timezone.now()
            existing_asset.save()
            asset = existing_asset
            logger.info(
                f"Replaced existing asset {asset.id} with new upload: "
                f"'{safe_filename}'"
            )
        else:
            # Create new asset record
            try:
                asset = BrandAsset.objects.create(
                    tenant=tenant,
                    company=company,
                    file_name=safe_filename,
                    file_type=file_type,
                    file_size=file.size,
                    gcs_path=landing_path,
                    gcs_bucket=actual_bucket,
                    processed=False,
                    pipeline_status="pending" if gcs_uploaded else "failed",
                    pipeline_error=(
                        "" if gcs_uploaded else "GCS not configured - file not stored"
                    ),
                )
            except IntegrityError:
                # Race condition: another request created the same asset
                return Response(
                    {
                        "error": "duplicate_file",
                        "message": f"A file named '{safe_filename}' already exists.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # Trigger data pipeline only if file was uploaded
        if gcs_uploaded:
            pipeline_service = get_pipeline_service()
            pipeline_service.publish_asset_event(asset)

        response_serializer = BrandAssetSerializer(asset)
        replaced = existing_asset is not None and replace_existing
        response_status = status.HTTP_200_OK if replaced else status.HTTP_201_CREATED
        return Response(response_serializer.data, status=response_status)

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
        # Get tenant from request (set by JWTTenantMiddleware)
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return Response(
                {"error": "No tenant context. Please log in again."},
                status=status.HTTP_403_FORBIDDEN,
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
        gcs_bucket = request.data.get(
            "gcs_bucket",
            tenant.get_raw_bucket() if tenant else "brand-automator-assets",
        )
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
            company = Company.objects.filter(id=company_id, tenant=tenant).first()
            if not company:
                return Response(
                    {
                        "error": "no_company",
                        "message": "Company not found.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            company = Company.objects.filter(tenant=tenant).first()
            if not company:
                return Response(
                    {
                        "error": "no_company",
                        "message": (
                            "No company found for this workspace. "
                            "Please complete onboarding first."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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

        # Check for duplicate file (same tenant + company + filename)
        replace_existing = str(request.data.get("replace_existing", "")).lower() in (
            "true",
            "1",
        )
        existing_asset = BrandAsset.objects.filter(
            tenant=tenant, company=company, file_name=safe_filename
        ).first()

        if existing_asset and not replace_existing:
            logger.info(
                f"Duplicate confirm_gcs_upload blocked: '{safe_filename}' "
                f"already exists as asset {existing_asset.id}"
            )
            return Response(
                {
                    "error": "duplicate_file",
                    "message": f"A file named '{safe_filename}' already exists.",
                    "existing_asset": {
                        "id": existing_asset.id,
                        "file_name": existing_asset.file_name,
                        "file_size": existing_asset.file_size,
                        "uploaded_at": existing_asset.uploaded_at.isoformat(),
                        "pipeline_status": existing_asset.pipeline_status,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )

        if existing_asset and replace_existing:
            # Delete old GCS blob (best-effort)
            old_gcs_path = existing_asset.gcs_path
            if old_gcs_path:
                try:
                    gcs_client = getattr(gcs_service, "client", None)
                    if gcs_client:
                        old_bucket_obj = gcs_client.bucket(
                            existing_asset.gcs_bucket or gcs_bucket
                        )
                        old_blob = old_bucket_obj.blob(old_gcs_path)
                        if old_blob.exists():
                            old_blob.delete()
                            logger.info(
                                f"Deleted old GCS file during confirm replacement: "
                                f"{old_gcs_path}"
                            )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete old GCS file '{old_gcs_path}' "
                        f"during confirm replacement: {e}"
                    )

            # Update existing record
            existing_asset.file_type = file_type
            existing_asset.file_size = file_size
            existing_asset.gcs_path = gcs_path
            existing_asset.gcs_bucket = gcs_bucket
            existing_asset.processed = False
            existing_asset.pipeline_status = "pending"
            existing_asset.pipeline_error = ""
            existing_asset.pipeline_trace_id = None
            existing_asset.uploaded_at = timezone.now()
            existing_asset.save()
            asset = existing_asset
            logger.info(
                f"Replaced existing asset {asset.id} via confirm_gcs_upload: "
                f"'{safe_filename}'"
            )
        else:
            # Create new asset record for the direct GCS upload
            try:
                asset = BrandAsset.objects.create(
                    tenant=tenant,
                    company=company,
                    file_name=safe_filename,
                    file_type=file_type,
                    file_size=file_size,
                    gcs_path=gcs_path,
                    gcs_bucket=gcs_bucket,
                    processed=False,
                    pipeline_status="pending",
                )
            except IntegrityError:
                return Response(
                    {
                        "error": "duplicate_file",
                        "message": f"A file named '{safe_filename}' already exists.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # Trigger data pipeline
        pipeline_service = get_pipeline_service()
        pipeline_service.publish_asset_event(asset)

        response_serializer = BrandAssetSerializer(asset)
        response_status = (
            status.HTTP_200_OK
            if (existing_asset and replace_existing)
            else status.HTTP_201_CREATED
        )
        return Response(response_serializer.data, status=response_status)

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


class OnboardingProgressViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for OnboardingProgress model.

    Permissions:
        - list, retrieve, current: IsTenantViewer
        - create, update, update_step: IsTenantEditor
    """

    queryset = OnboardingProgress.objects.all()
    serializer_class = OnboardingProgressSerializer
    permission_classes = [IsAuthenticated]
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "current": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "update": [IsAuthenticated, IsTenantEditor],
        "partial_update": [IsAuthenticated, IsTenantEditor],
        "update_step": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        # Filter by tenant in multi-tenant setup
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            return OnboardingProgress.objects.filter(tenant=tenant)
        return OnboardingProgress.objects.none()

    def perform_create(self, serializer):
        """Attach active tenant on progress creation."""
        tenant = getattr(self.request, "tenant", None)
        serializer.save(tenant=tenant)

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current onboarding progress for the tenant"""
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return Response(
                {"error": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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

        # Get tenant defensively
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return Response(
                {"error": "Tenant context required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
