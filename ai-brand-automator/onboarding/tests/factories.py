"""
Factory Boy factories for onboarding models
"""
import factory
from factory.django import DjangoModelFactory
from onboarding.models import Company, BrandAsset, OnboardingProgress


class CompanyFactory(DjangoModelFactory):
    """Factory for Company model"""

    class Meta:
        model = Company

    name = factory.Faker("company")
    description = factory.Faker("paragraph", nb_sentences=3)
    industry = factory.Faker(
        "random_element",
        elements=[
            "Technology",
            "Healthcare",
            "Finance",
            "E-commerce",
            "Manufacturing",
            "Education",
            "Retail",
            "Consulting",
        ],
    )
    target_audience = factory.Faker("paragraph", nb_sentences=2)
    core_problem = factory.Faker("sentence", nb_words=10)
    brand_voice = factory.Faker(
        "random_element",
        elements=[
            "professional",
            "friendly",
            "bold",
            "authoritative",
            "playful",
            "innovative",
            "warm",
            "technical",
        ],
    )

    # AI-generated fields (optional)
    vision_statement = factory.Faker("sentence", nb_words=12)
    mission_statement = factory.Faker("sentence", nb_words=15)
    values = factory.LazyFunction(
        lambda: "Innovation, Excellence, Integrity, Customer Focus"
    )
    positioning_statement = factory.Faker("paragraph", nb_sentences=2)

    # Additional messaging
    tagline = factory.Faker("catch_phrase")
    value_proposition = factory.Faker("sentence", nb_words=10)
    elevator_pitch = factory.Faker("paragraph", nb_sentences=3)

    # Brand identity fields
    color_palette_desc = factory.LazyFunction(
        lambda: "Primary: #0066CC, Secondary: #FF6600, Accent: #00CC66"
    )
    font_recommendations = factory.LazyFunction(
        lambda: "Headings: Montserrat Bold, Body: Open Sans Regular"
    )
    messaging_guide = factory.Faker("paragraph", nb_sentences=4)

    # tenant must be provided explicitly
    tenant = None


class BrandAssetFactory(DjangoModelFactory):
    """Factory for BrandAsset model"""

    class Meta:
        model = BrandAsset

    file_name = factory.Sequence(lambda n: f"asset_{n}.jpg")
    file_type = factory.Faker(
        "random_element", elements=["image", "video", "document", "other"]
    )
    file_size = factory.Faker("random_int", min=1024, max=5242880)  # 1KB to 5MB

    # Storage fields
    gcs_path = factory.LazyAttribute(
        lambda obj: f"assets/{obj.tenant.schema_name}/{obj.file_name}"
    )
    gcs_bucket = "brand-automator-assets"

    # Metadata
    processed = False

    # tenant and company must be provided
    tenant = None
    company = None


class ImageAssetFactory(BrandAssetFactory):
    """Factory specifically for image assets"""

    file_name = factory.Sequence(lambda n: f"image_{n}.jpg")
    file_type = "image"
    file_size = factory.Faker("random_int", min=102400, max=2097152)  # 100KB to 2MB


class DocumentAssetFactory(BrandAssetFactory):
    """Factory specifically for document assets"""

    file_name = factory.Sequence(lambda n: f"document_{n}.pdf")
    file_type = "document"
    file_size = factory.Faker("random_int", min=51200, max=1048576)  # 50KB to 1MB


class OnboardingProgressFactory(DjangoModelFactory):
    """Factory for OnboardingProgress model"""

    class Meta:
        model = OnboardingProgress

    current_step = "company_info"
    completed_steps = factory.LazyFunction(list)
    is_completed = False

    # tenant and company must be provided
    tenant = None
    company = None


class CompletedOnboardingProgressFactory(OnboardingProgressFactory):
    """Factory for completed onboarding"""

    current_step = "review"
    completed_steps = factory.LazyFunction(
        lambda: [
            "company_info",
            "brand_strategy",
            "brand_identity",
            "assets_upload",
            "review",
        ]
    )
    is_completed = True
