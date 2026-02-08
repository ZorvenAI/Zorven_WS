from django.db import models
from django.utils import timezone
from tenants.models import Tenant


class Company(models.Model):
    """
    Company/Brand information collected during onboarding
    """

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="company",
        null=True,
        blank=True,
        help_text="Tenant (optional in MVP mode)",
    )
    name = models.CharField(max_length=255, help_text="Company/Brand name")
    description = models.TextField(blank=True, help_text="Brief company description")
    industry = models.CharField(max_length=100, blank=True, help_text="Industry sector")
    target_audience = models.TextField(
        blank=True, help_text="Description of target customers"
    )
    core_problem = models.TextField(
        blank=True, help_text="Main problem the company solves"
    )

    # Target audience details (added in 0004 migration)
    demographics = models.TextField(
        blank=True, help_text="Demographic characteristics of target audience"
    )
    psychographics = models.TextField(
        blank=True, help_text="Psychological characteristics, values, interests"
    )
    pain_points = models.TextField(
        blank=True, help_text="Customer pain points and challenges"
    )
    desired_outcomes = models.TextField(
        blank=True, help_text="What customers want to achieve"
    )

    brand_voice = models.CharField(
        max_length=50,
        choices=[
            ("professional", "Professional"),
            ("friendly", "Friendly"),
            ("bold", "Bold"),
            ("authoritative", "Authoritative"),
            ("playful", "Playful"),
            ("innovative", "Innovative"),
            ("warm", "Warm"),
            ("technical", "Technical"),
        ],
        blank=True,
        help_text="Brand personality/voice",
    )

    # AI-generated content
    vision_statement = models.TextField(
        blank=True, help_text="AI-generated vision statement"
    )
    mission_statement = models.TextField(
        blank=True, help_text="AI-generated mission statement"
    )
    values = models.TextField(
        blank=True, default="", help_text="Comma-separated list of core values"
    )
    positioning_statement = models.TextField(
        blank=True, help_text="Market positioning statement"
    )

    # Additional messaging
    tagline = models.CharField(
        max_length=255, blank=True, help_text="Brand tagline/slogan"
    )
    value_proposition = models.TextField(blank=True, help_text="Key value proposition")
    elevator_pitch = models.TextField(blank=True, help_text="30-second elevator pitch")

    # Brand identity (AI-generated)
    color_palette_desc = models.TextField(
        blank=True, help_text="Color palette recommendations"
    )
    font_recommendations = models.TextField(
        blank=True, help_text="Typography recommendations"
    )
    messaging_guide = models.TextField(
        blank=True, help_text="Brand messaging guidelines"
    )

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class BrandAsset(models.Model):
    """
    Uploaded brand assets (images, videos, documents)
    """

    PIPELINE_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("ingested", "Ingested"),
        ("curated", "Curated"),
        ("indexed", "Indexed"),
        ("failed", "Failed"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="brand_assets",
        null=True,
        blank=True,
        help_text="Tenant (optional in MVP mode)",
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="assets"
    )

    file_name = models.CharField(max_length=255, help_text="Original file name")
    file_type = models.CharField(
        max_length=50,
        choices=[
            ("image", "Image"),
            ("video", "Video"),
            ("document", "Document"),
            ("other", "Other"),
        ],
        help_text="Type of file",
    )
    file_size = models.PositiveIntegerField(help_text="File size in bytes")

    # Storage information
    gcs_path = models.CharField(max_length=500, help_text="Google Cloud Storage path")
    gcs_bucket = models.CharField(max_length=100, default="brand-automator-assets")

    # Metadata
    uploaded_at = models.DateTimeField(default=timezone.now)
    processed = models.BooleanField(
        default=False, help_text="Whether file has been processed"
    )

    # Pipeline tracking fields
    pipeline_status = models.CharField(
        max_length=20,
        choices=PIPELINE_STATUS_CHOICES,
        default="pending",
        help_text="Current status in the data pipeline",
    )
    pipeline_error = models.TextField(
        blank=True,
        default="",
        help_text="Error message if pipeline processing failed",
    )
    pipeline_trace_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Trace ID for tracking through the pipeline",
    )

    class Meta:
        verbose_name = "Brand Asset"
        verbose_name_plural = "Brand Assets"
        ordering = ["-uploaded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "company", "file_name"],
                name="unique_brand_asset_per_tenant_company",
            ),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.company.name})"


class OnboardingProgress(models.Model):
    """
    Tracks onboarding completion progress
    """

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="onboarding_progress",
        null=True,
        blank=True,
        help_text="Tenant (optional in MVP mode)",
    )
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="onboarding_progress"
    )

    # Progress tracking
    current_step = models.CharField(
        max_length=50,
        default="company_info",
        choices=[
            ("company_info", "Company Information"),
            ("brand_strategy", "Brand Strategy"),
            ("brand_identity", "Brand Identity"),
            ("assets_upload", "Assets Upload"),
            ("review", "Review & Complete"),
        ],
        help_text="Current onboarding step",
    )

    completed_steps = models.JSONField(
        default=list, help_text="List of completed step identifiers"
    )
    is_completed = models.BooleanField(
        default=False, help_text="Whether onboarding is fully complete"
    )

    # Timestamps
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Onboarding Progress"
        verbose_name_plural = "Onboarding Progress"

    def __str__(self):
        return f"{self.tenant.name} - {self.current_step}"

    @property
    def completion_percentage(self):
        """Calculate completion percentage based on completed steps"""
        total_steps = (
            5  # company_info, brand_strategy, brand_identity, assets_upload, review
        )
        completed_count = len(self.completed_steps)
        return min(100, int((completed_count / total_steps) * 100))
