from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Company, BrandAsset, OnboardingProgress
from .serializers import (
    CompanySerializer,
    BrandAssetSerializer,
    OnboardingProgressSerializer,
    CompanyCreateSerializer,
    CompanyUpdateSerializer,
    BrandAssetUploadSerializer,
)
from files.services import gcs_service
from ai_services.services import ai_service
from brand_automator.validators import validate_file_upload, sanitize_filename


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

        # Save file locally first (MVP mode - local storage fallback)
        from django.core.files.storage import default_storage

        local_path = f"assets/{tenant.id}/{safe_filename}"
        saved_path = default_storage.save(local_path, file)

        # Try to upload to Google Cloud Storage (optional for MVP)
        gcs_path = f"assets/{tenant.id}/{safe_filename}"
        gcs_uploaded = False
        try:
            if gcs_service.client and gcs_service.bucket:
                gcs_service.upload_file(file, gcs_path, file.content_type)
                gcs_uploaded = True
        except Exception as e:
            # GCS upload failed, but we have local copy - log and continue
            print(f"GCS upload failed (using local storage): {str(e)}")

        # Create asset record
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name=safe_filename,
            file_type=file_type,
            file_size=file.size,
            gcs_path=gcs_path if gcs_uploaded else saved_path,
            processed=True,
        )

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

        # Create asset record for the direct GCS upload
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name=safe_filename,
            file_type=file_type,
            file_size=file_size,
            gcs_path=gcs_path,
            gcs_bucket=gcs_bucket,
            processed=True,  # Already uploaded to GCS by Kong
        )

        response_serializer = BrandAssetSerializer(asset)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


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
