"""
Global pytest fixtures and configuration
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from hypothesis import settings

# ============================================
# Mock Kafka BEFORE any imports to prevent slow connection attempts
# ============================================
mock_producer = MagicMock()
mock_producer.produce = MagicMock()
mock_producer.flush = MagicMock()
mock_producer.poll = MagicMock(return_value=0)

mock_consumer = MagicMock()
mock_consumer.subscribe = MagicMock()
mock_consumer.poll = MagicMock(return_value=None)
mock_consumer.close = MagicMock()

# Create mock confluent_kafka module
mock_confluent_kafka = MagicMock()
mock_confluent_kafka.Producer = MagicMock(return_value=mock_producer)
mock_confluent_kafka.Consumer = MagicMock(return_value=mock_consumer)
mock_confluent_kafka.KafkaError = MagicMock()
mock_confluent_kafka.KafkaException = Exception

# Create mock admin submodule
mock_admin = MagicMock()
mock_admin.AdminClient = MagicMock()
mock_admin.NewTopic = MagicMock()

# Inject mocks before any real imports
sys.modules["confluent_kafka"] = mock_confluent_kafka
sys.modules["confluent_kafka.admin"] = mock_admin

# Exclude standalone test scripts from pytest collection
# test_mcp_server.py is designed to be run manually, not with pytest
collect_ignore = ["test_mcp_server.py"]

# Load test environment variables before Django initializes
test_env_path = Path(__file__).parent / ".env.test"
if test_env_path.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(test_env_path)
    except ImportError:
        # python-dotenv not installed, skip loading .env.test
        pass

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

User = get_user_model()

# Hypothesis profiles for different environments
settings.register_profile("ci", max_examples=200, deadline=1000)
settings.register_profile("dev", max_examples=50, deadline=500)
settings.load_profile("dev")


@pytest.fixture(scope="session", autouse=True)
def setup_public_tenant(django_db_setup, django_db_blocker):
    """Create public tenant with localhost domain for tests

    This is required for django-tenants middleware to work in tests.
    """
    from tenants.models import Tenant, Domain
    from django.db import connection

    with django_db_blocker.unblock():
        connection.set_schema_to_public()

        # Create or get public tenant
        tenant, created = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={
                "name": "Public Test Tenant",
                "subscription_status": "active",
                "max_users": 100,
                "storage_limit_gb": 10,
            },
        )

        # Create localhost domain if it doesn't exist
        Domain.objects.get_or_create(
            domain="localhost", defaults={"tenant": tenant, "is_primary": True}
        )


@pytest.fixture(autouse=True)
def reset_to_public_schema(db):
    """Reset to public schema after each test to prevent tenant isolation issues"""
    yield
    from django.db import connection

    try:
        connection.set_schema_to_public()
    except Exception:
        pass  # Ignore if not in tenant context


@pytest.fixture
def api_client():
    """DRF API test client with tenant middleware support"""
    client = APIClient()
    # Set SERVER_NAME for tenant middleware (django-tenants requirement)
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def user(db):
    """Create test user"""
    return User.objects.create_user(
        username="testuser", email="test@example.com", password="TestPass123!"
    )


@pytest.fixture
def admin_user(db):
    """Create admin user for testing admin-only features"""
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="AdminPass123!",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated with test user

    Sets SERVER_NAME='localhost' to bypass tenant middleware for tests
    """
    api_client.force_authenticate(user=user)
    # Set default SERVER_NAME for tenant middleware
    api_client.defaults["SERVER_NAME"] = "localhost"
    return api_client


@pytest.fixture
def authenticated_client_with_tenant(api_client, user, public_tenant):
    """API client authenticated with test user and tenant context.

    Relies on the test handler's `_force_tenant` attribute to ensure
    request.tenant is available in views that use defensive tenant access.
    """
    api_client.force_authenticate(user=user)
    api_client.defaults["SERVER_NAME"] = "localhost"

    # Add tenant to handler so middleware/handler logic can set request.tenant
    api_client.handler._force_tenant = public_tenant
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """API client authenticated as admin"""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def public_tenant(db):
    """Get the public tenant for tests (created by setup_public_tenant)"""
    from tenants.models import Tenant

    return Tenant.objects.get(schema_name="public")


@pytest.fixture
def unique_tenant(db):
    """
    Create a unique tenant for each test invocation.

    Essential for property tests using Hypothesis to avoid
    OneToOne constraint violations.
    """
    from tenants.models import Tenant, Domain
    from django.db import connection
    import uuid

    # Ensure we're in public schema for tenant creation
    connection.set_schema_to_public()

    # Generate unique schema name
    unique_id = uuid.uuid4().hex[:10]
    schema_name = f"test_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"Test Tenant {unique_id}",
        schema_name=schema_name,
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(
        tenant=tenant,
        domain=f"{schema_name}.localhost",
        is_primary=True,
    )

    return tenant


@pytest.fixture
def tenant(db):
    """Create test tenant with domain (function-scoped for tests that modify tenant)"""
    from tenants.models import Tenant, Domain
    from django.db import connection

    # Ensure we're in public schema for tenant creation
    connection.set_schema_to_public()

    tenant = Tenant.objects.create(
        name="Test Company",
        schema_name="tenant_test",
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(
        tenant=tenant,
        domain="test.localhost",
        is_primary=True,
    )

    return tenant


@pytest.fixture(scope="module")
def shared_tenant(django_db_setup, django_db_blocker):
    """Module-scoped tenant for read-only tests (much faster)"""
    from tenants.models import Tenant, Domain
    from django.db import connection

    with django_db_blocker.unblock():
        # Ensure we're in public schema for tenant creation
        connection.set_schema_to_public()

        tenant = Tenant.objects.create(
            name="Shared Test Tenant",
            schema_name="tenant_shared",
            subscription_status="active",
            max_users=10,
            storage_limit_gb=5,
        )
        Domain.objects.create(
            tenant=tenant,
            domain="shared.localhost",
            is_primary=True,
        )

        yield tenant

        # Cleanup after module
        connection.set_schema_to_public()
        tenant.delete()


@pytest.fixture
def tenant2(db):
    """Create second tenant for multi-tenancy isolation tests"""
    from tenants.models import Tenant, Domain
    from django.db import connection

    # Ensure we're in public schema for tenant creation
    connection.set_schema_to_public()

    tenant = Tenant.objects.create(
        name="Second Company",
        schema_name="tenant_second",
        subscription_status="active",
    )
    Domain.objects.create(
        tenant=tenant,
        domain="second.localhost",
        is_primary=True,
    )

    return tenant
    return tenant


@pytest.fixture
def tenant_with_buckets(db, setup_public_tenant):
    """Create a tenant with custom per-tenant GCS buckets."""
    from tenants.models import Tenant, Domain

    tenant = Tenant.objects.create(
        name="Tenant With Buckets",
        schema_name="tenant_buckets",
        subscription_status="active",
        gcs_raw_bucket="tenant-custom-raw",
        gcs_curated_bucket="tenant-custom-curated",
    )
    Domain.objects.create(
        tenant=tenant,
        domain="buckets.localhost",
        is_primary=True,
    )
    return tenant


@pytest.fixture
def mock_gemini_api(mocker):
    """Mock Gemini AI API responses"""
    mock_response = {
        "vision_statement": "To revolutionize the industry through innovation",
        "mission_statement": "We deliver exceptional value to our customers",
        "values": "Innovation, Excellence, Integrity",
        "positioning_statement": "The leader in innovative solutions",
    }
    return mocker.patch(
        "ai_services.services.GeminiAIService.generate_brand_strategy",
        return_value=mock_response,
    )


# --- Membership fixtures ---


@pytest.fixture
def membership_owner(tenant, user):
    """User as OWNER of tenant."""
    from tenants.models import Membership

    return Membership.objects.create(
        user=user,
        tenant=tenant,
        role=Membership.Role.OWNER,
    )


@pytest.fixture
def membership_admin(tenant, db):
    """A different user as ADMIN of tenant."""
    admin_member = User.objects.create_user(
        username="admin_member",
        email="adminmember@test.com",
        password="TestPass123!",
    )
    from tenants.models import Membership

    return Membership.objects.create(
        user=admin_member,
        tenant=tenant,
        role=Membership.Role.ADMIN,
    )


@pytest.fixture
def membership_editor(tenant, db):
    """A different user as EDITOR of tenant."""
    editor = User.objects.create_user(
        username="editor",
        email="editor@test.com",
        password="TestPass123!",
    )
    from tenants.models import Membership

    return Membership.objects.create(
        user=editor,
        tenant=tenant,
        role=Membership.Role.EDITOR,
    )


@pytest.fixture
def membership_viewer(tenant, db):
    """A different user as VIEWER of tenant."""
    viewer = User.objects.create_user(
        username="viewer",
        email="viewer@test.com",
        password="TestPass123!",
    )
    from tenants.models import Membership

    return Membership.objects.create(
        user=viewer,
        tenant=tenant,
        role=Membership.Role.VIEWER,
    )


@pytest.fixture
def mock_gemini_identity(mocker):
    """Mock Gemini AI brand identity generation"""
    mock_response = {
        "color_palette_desc": "Primary: #0066CC, Secondary: #FF6600",
        "font_recommendations": "Headings: Montserrat Bold, Body: Open Sans",
        "messaging_guide": "Professional yet approachable tone",
    }
    return mocker.patch(
        "ai_services.services.GeminiAIService.generate_brand_identity",
        return_value=mock_response,
    )


@pytest.fixture
def mock_gemini_market_analysis(mocker):
    """Mock Gemini AI market analysis"""
    mock_response = {
        "market_size": "$10B",
        "growth_rate": "15% annually",
        "key_trends": ["AI adoption", "Cloud migration", "Remote work"],
        "competitors": ["Company A", "Company B"],
    }
    return mocker.patch(
        "ai_services.services.GeminiAIService.analyze_market",
        return_value=mock_response,
    )


@pytest.fixture
def mock_gcs_upload(mocker):
    """Mock Google Cloud Storage file uploads"""
    return mocker.patch(
        "files.services.GCSService.upload_file",
        return_value="https://storage.googleapis.com/test-bucket/test-file.jpg",
    )


@pytest.fixture
def mock_gcs_delete(mocker):
    """Mock Google Cloud Storage file deletion"""
    return mocker.patch("files.services.GCSService.delete_file", return_value=True)


@pytest.fixture(autouse=True)
def mock_email_backend(settings):
    """Auto-mock email backend for all tests"""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def mock_request_tenant(mocker, tenant):
    """Mock request.tenant attribute for multi-tenancy tests"""

    def _mock_request(request):
        request.tenant = tenant
        return request

    return _mock_request


@pytest.fixture
def sample_uploaded_file():
    """Create a sample uploaded file for testing"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        "test_image.jpg",
        b"fake image content",
        content_type="image/jpeg",
    )


@pytest.fixture
def sample_pdf_file():
    """Create a sample PDF file for testing"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        "test_document.pdf",
        b"%PDF-1.4 fake pdf content",
        content_type="application/pdf",
    )
