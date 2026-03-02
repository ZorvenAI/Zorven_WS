"""
Unit tests for ai_services views.
Tests ChatSessionViewSet, AIGenerationViewSet, and API endpoints.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from rest_framework import status
from django.urls import reverse

from ai_services.tests.factories import (
    ChatSessionFactory,
    ChatMessageFactory,
    AIGenerationFactory,
)
from onboarding.tests.factories import CompanyFactory


@pytest.mark.django_db
@pytest.mark.unit
class TestChatSessionViewSet:
    """Tests for ChatSessionViewSet"""

    def url_list(self):
        return reverse("chatsession-list")

    def url_detail(self, pk):
        return reverse("chatsession-detail", kwargs={"pk": pk})

    def test_list_sessions_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list sessions"""
        response = api_client.get(self.url_list())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_sessions_authenticated(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test listing chat sessions for authenticated user"""
        # Create sessions for this tenant
        ChatSessionFactory(tenant=public_tenant)
        ChatSessionFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.get(self.url_list())
        assert response.status_code == status.HTTP_200_OK

    def test_create_session_authenticated(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test creating a chat session"""
        data = {
            "session_id": str(uuid.uuid4()),
            "title": "New Chat Session",
            "messages": [],
            "context": {"test": "data"},
        }

        response = authenticated_client_with_tenant.post(
            self.url_list(), data, format="json"
        )
        # Authenticated users with proper tenant context should be able to create
        assert response.status_code == status.HTTP_201_CREATED

    def test_retrieve_session(self, authenticated_client_with_tenant, public_tenant):
        """Test retrieving a single chat session"""
        session = ChatSessionFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.get(self.url_detail(session.id))
        # Session exists for this tenant, so it should be retrievable
        assert response.status_code == status.HTTP_200_OK

    def test_delete_session(self, authenticated_client_with_tenant, public_tenant):
        """Test deleting a chat session"""
        session = ChatSessionFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.delete(self.url_detail(session.id))
        # Deleting an existing session should succeed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_messages_endpoint(self, authenticated_client_with_tenant, public_tenant):
        """Test retrieving messages for a session via nested endpoint"""
        session = ChatSessionFactory(tenant=public_tenant)
        ChatMessageFactory(session=session, role="user", content="Hi")
        ChatMessageFactory(session=session, role="assistant", content="Hello!")

        url = reverse("chatsession-messages", kwargs={"pk": session.pk})
        response = authenticated_client_with_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Response is paginated: {count, results, ...}
        results = response.data.get("results", response.data)
        if isinstance(results, dict):
            results = results.get("results", [])
        assert len(results) == 2
        assert results[0]["role"] == "user"
        assert results[0]["content"] == "Hi"
        assert results[1]["role"] == "assistant"
        assert results[1]["content"] == "Hello!"


@pytest.mark.django_db
@pytest.mark.unit
class TestAIGenerationViewSet:
    """Tests for AIGenerationViewSet (read-only)"""

    def url_list(self):
        return reverse("aigeneration-list")

    def url_detail(self, pk):
        return reverse("aigeneration-detail", kwargs={"pk": pk})

    def test_list_generations_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list generations"""
        response = api_client.get(self.url_list())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_generations_authenticated(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test listing AI generations for authenticated user"""
        AIGenerationFactory(tenant=public_tenant)
        AIGenerationFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.get(self.url_list())
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_generation(self, authenticated_client_with_tenant, public_tenant):
        """Test retrieving a single AI generation"""
        generation = AIGenerationFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.get(self.url_detail(generation.id))
        assert response.status_code == status.HTTP_200_OK

    def test_cannot_create_generation_directly(self, authenticated_client):
        """Test that generations cannot be created via API (read-only)"""
        data = {
            "content_type": "brand_strategy",
            "prompt": "Test",
            "response": "Response",
        }

        response = authenticated_client.post(self.url_list(), data, format="json")
        # ReadOnlyModelViewSet doesn't allow POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_cannot_delete_generation(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test that generations cannot be deleted via API (read-only)"""
        generation = AIGenerationFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.delete(
            self.url_detail(generation.id)
        )
        # ReadOnlyModelViewSet doesn't allow DELETE
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
@pytest.mark.unit
class TestChatWithAIEndpoint:
    """Tests for chat_with_ai endpoint"""

    def url(self):
        return reverse("chat_with_ai")

    def test_chat_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot chat"""
        response = api_client.post(self.url(), {"message": "Hello"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_chat_missing_message(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test chat with missing message field"""
        response = authenticated_client_with_tenant.post(self.url(), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_empty_message(self, authenticated_client_with_tenant, public_tenant):
        """Test chat with empty message"""
        response = authenticated_client_with_tenant.post(
            self.url(), {"message": ""}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ai_services.views._maybe_auto_title")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_chat_with_valid_message(
        self,
        mock_ai_service,
        mock_classify,
        mock_auto_title,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Test chat with valid message returns dict response"""
        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai_service.chat_with_brand_context.return_value = {
            "content": "AI Response",
            "thinking": "",
        }

        response = authenticated_client_with_tenant.post(
            self.url(), {"message": "Hello, AI!"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert mock_ai_service.chat_with_brand_context.called
        assert response.data["pipeline_job"] is None
        assert response.data["response"] == "AI Response"
        assert "thinking" in response.data

    @patch("ai_services.views._maybe_auto_title")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_chat_creates_chat_message_records(
        self,
        mock_ai_service,
        mock_classify,
        mock_auto_title,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Test that chat creates ChatMessage records instead of JSONField"""
        from ai_services.models import ChatMessage, ChatSession

        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai_service.chat_with_brand_context.return_value = {
            "content": "AI Response",
            "thinking": "Let me think...",
        }

        response = authenticated_client_with_tenant.post(
            self.url(), {"message": "Hello, AI!"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        session_id = response.data["session_id"]
        session = ChatSession.objects.get(session_id=session_id)

        # Should have 2 ChatMessage records (user + assistant)
        messages = ChatMessage.objects.filter(session=session).order_by("created_at")
        assert messages.count() == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello, AI!"
        assert messages[1].role == "assistant"
        assert messages[1].content == "AI Response"


@pytest.mark.django_db
@pytest.mark.unit
class TestGenerateBrandStrategyEndpoint:
    """Tests for generate_brand_strategy endpoint"""

    def url(self):
        return reverse("generate_brand_strategy")

    def test_generate_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot generate"""
        response = api_client.post(self.url(), {"company_id": 1})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_generate_missing_company_id(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test generate with missing company_id"""
        response = authenticated_client_with_tenant.post(self.url(), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_invalid_company_id(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test generate with invalid company_id type"""
        response = authenticated_client_with_tenant.post(
            self.url(), {"company_id": "invalid"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ai_services.views.ai_service")
    def test_generate_company_not_found(
        self, mock_ai_service, authenticated_client_with_tenant
    ):
        """Test generate with non-existent company"""
        response = authenticated_client_with_tenant.post(
            self.url(), {"company_id": 99999}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("ai_services.views.ai_service")
    def test_generate_success(
        self, mock_ai_service, authenticated_client_with_tenant, public_tenant
    ):
        """Test successful brand strategy generation"""
        # Create company for tenant
        company = CompanyFactory(tenant=public_tenant)

        mock_ai_service.generate_brand_strategy.return_value = {
            "vision_statement": "Our vision",
            "mission_statement": "Our mission",
            "values": "Innovation, Excellence",
            "positioning_statement": "We are leaders",
        }

        response = authenticated_client_with_tenant.post(
            self.url(), {"company_id": company.id}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "data" in response.data


@pytest.mark.django_db
@pytest.mark.unit
class TestGenerateBrandIdentityEndpoint:
    """Tests for generate_brand_identity endpoint"""

    def url(self):
        return reverse("generate_brand_identity")

    def test_generate_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot generate"""
        response = api_client.post(self.url(), {"company_id": 1})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_generate_missing_company_id(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test generate with missing company_id"""
        response = authenticated_client_with_tenant.post(self.url(), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ai_services.views.ai_service")
    def test_generate_success(
        self, mock_ai_service, authenticated_client_with_tenant, public_tenant
    ):
        """Test successful brand identity generation"""
        company = CompanyFactory(tenant=public_tenant)

        mock_ai_service.generate_brand_identity.return_value = {
            "color_palette_desc": "Blue, White, Gray",
            "font_recommendations": "Open Sans, Roboto",
            "messaging_guide": "Speak clearly and confidently",
        }

        response = authenticated_client_with_tenant.post(
            self.url(), {"company_id": company.id}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True


@pytest.mark.django_db
@pytest.mark.unit
class TestAnalyzeMarketEndpoint:
    """Tests for analyze_market endpoint"""

    def url(self):
        return reverse("analyze_market")

    def test_analyze_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot analyze"""
        response = api_client.post(self.url(), {"company_id": 1})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_analyze_missing_company_id(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test analyze with missing company_id"""
        response = authenticated_client_with_tenant.post(self.url(), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ai_services.views.ai_service")
    def test_analyze_success(
        self, mock_ai_service, authenticated_client_with_tenant, public_tenant
    ):
        """Test successful market analysis"""
        company = CompanyFactory(tenant=public_tenant)

        mock_ai_service.analyze_market.return_value = {
            "market_size": "Large",
            "competitors": ["Competitor A", "Competitor B"],
            "opportunities": ["Opportunity 1"],
        }

        response = authenticated_client_with_tenant.post(
            self.url(), {"company_id": company.id}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True


@pytest.mark.django_db
@pytest.mark.unit
class TestChatWithAIPipelineIntegration:
    """Tests for pipeline dispatch via chat endpoint."""

    def url(self):
        return reverse("chat_with_ai")

    @patch("orchestration.tasks.dispatch_job_task")
    @patch("ai_services.services.GeminiAIService.extract_target_brand")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    def test_analysis_message_triggers_pipeline(
        self,
        mock_classify,
        mock_extract,
        mock_dispatch,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Analysis request should create job and return pipeline_job."""
        mock_classify.return_value = {"intent": "pipeline", "confidence": 0.9}
        mock_extract.return_value = {
            "company_name": "Acme Corp",
            "sector": "technology",
            "base_revenue": 1_000_000,
            "growth_rate": 0.05,
            "brand_awareness": 50,
            "profit_margin": 0.10,
        }

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"message": "Perform a brand valuation analysis for Acme Corp"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pipeline_job"] is not None
        assert "job_id" in response.data["pipeline_job"]
        assert response.data["pipeline_job"]["status"] == "queued"
        mock_dispatch.delay.assert_called_once()

    @patch("ai_services.views._maybe_auto_title")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_conversational_message_no_pipeline(
        self,
        mock_ai,
        mock_classify,
        mock_auto_title,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Conversational message should NOT trigger pipeline."""
        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai.chat_with_brand_context.return_value = {
            "content": "Hello!",
            "thinking": "",
        }

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"message": "What is a brand voice?"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pipeline_job"] is None
        assert response.data["response"] == "Hello!"

    @patch("orchestration.tasks.dispatch_job_task")
    @patch("ai_services.services.GeminiAIService.extract_target_brand")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    def test_pipeline_job_linked_to_session(
        self,
        mock_classify,
        mock_extract,
        mock_dispatch,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Pipeline job should record chat session_id in input_context."""
        mock_classify.return_value = {"intent": "pipeline", "confidence": 0.8}
        mock_extract.return_value = {
            "company_name": "Test Brand",
            "sector": "technology",
            "base_revenue": 5_000_000,
            "growth_rate": 0.08,
            "brand_awareness": 60,
            "profit_margin": 0.12,
        }

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"message": "Run a brand equity analysis"},
            format="json",
        )

        from orchestration.models import AnalysisJob

        job = AnalysisJob.objects.get(job_id=response.data["pipeline_job"]["job_id"])
        assert job.input_context["source"] == "chat"
        assert job.input_context["session_id"] == response.data["session_id"]

    @patch("orchestration.tasks.dispatch_job_task")
    @patch("ai_services.services.GeminiAIService.extract_target_brand")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    def test_pipeline_job_excludes_financial_data(
        self,
        mock_classify,
        mock_extract,
        mock_dispatch,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Financial data NOT in job_context — intel agent looks up."""
        mock_classify.return_value = {"intent": "pipeline", "confidence": 0.9}
        mock_extract.return_value = {
            "company_name": "Nike",
            "sector": "consumer_goods",
            "base_revenue": 51_000_000_000,
            "growth_rate": 0.10,
            "brand_awareness": 95,
            "profit_margin": 0.12,
            "customer_loyalty": 82,
            "market_share": 0.27,
        }

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"message": "Calculate brand equity for Nike"},
            format="json",
        )

        from orchestration.models import AnalysisJob

        job = AnalysisJob.objects.get(job_id=response.data["pipeline_job"]["job_id"])
        # company_name and sector should be present
        assert job.input_context["company_name"] == "Nike"
        assert job.input_context["sector"] == "consumer_goods"
        # Financial data should NOT be in job_context
        for key in (
            "base_revenue",
            "growth_rate",
            "brand_awareness",
            "profit_margin",
            "customer_loyalty",
            "market_share",
        ):
            assert key not in job.input_context, (
                f"{key} should not be in job_context — "
                f"intelligence agent does its own lookup"
            )

    @patch("orchestration.tasks.dispatch_job_task")
    @patch("ai_services.services.GeminiAIService.extract_target_brand")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    def test_chat_pipeline_uses_auto_detect(
        self,
        mock_classify,
        mock_extract,
        mock_dispatch,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Chat pipelines always use auto-detect (no manifest)."""
        mock_classify.return_value = {
            "intent": "pipeline",
            "confidence": 0.9,
        }
        mock_extract.return_value = {
            "company_name": "Nike",
            "sector": "consumer_goods",
        }

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"message": "Calculate brand equity for Nike"},
            format="json",
        )

        from orchestration.models import AnalysisJob

        job = AnalysisJob.objects.get(job_id=response.data["pipeline_job"]["job_id"])
        assert (
            job.manifest is None
        ), "Chat jobs should use auto-detect, not a fixed manifest"


@pytest.mark.django_db
@pytest.mark.unit
class TestUploadChatAttachmentEndpoint:
    """Tests for upload_chat_attachment endpoint"""

    def url(self):
        return reverse("upload_chat_attachment")

    def test_upload_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot upload"""
        response = api_client.post(self.url(), {})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_no_file(self, authenticated_client_with_tenant, public_tenant):
        """Test upload without a file"""
        response = authenticated_client_with_tenant.post(
            self.url(),
            {"session_id": "abc", "message_id": "1"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No file" in response.data["error"]

    def test_upload_missing_session_id(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test upload without session_id"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        response = authenticated_client_with_tenant.post(
            self.url(),
            {"file": f, "message_id": "1"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("files.services.gcs_service")
    def test_upload_success(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Test successful file upload creates SessionAttachment"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ai_services.models import SessionAttachment

        # Setup: mock GCS to skip real upload
        mock_gcs.get_bucket.return_value = None  # GCS not configured

        CompanyFactory(tenant=public_tenant)
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(session=session, role="user", content="Upload test")

        f = SimpleUploadedFile(
            "test.pdf", b"pdf-content", content_type="application/pdf"
        )
        response = authenticated_client_with_tenant.post(
            self.url(),
            {
                "file": f,
                "session_id": session.session_id,
                "message_id": str(msg.id),
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["file_name"] == "test.pdf"
        assert response.data["file_type"] == "document"
        assert SessionAttachment.objects.filter(message=msg).count() == 1

    def test_upload_invalid_session(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test upload with non-existent session"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        response = authenticated_client_with_tenant.post(
            self.url(),
            {
                "file": f,
                "session_id": "nonexistent-uuid",
                "message_id": "999",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.unit
class TestChatWriteLock:
    """Tests for Redis write lock in chat_with_ai."""

    def url(self):
        return reverse("chat_with_ai")

    @patch("ai_services.views._maybe_auto_title")
    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_write_lock_prevents_concurrent_sends(
        self,
        mock_ai,
        mock_classify,
        mock_title,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Second send to same session should be rejected while lock held."""
        from django.core.cache import cache

        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai.chat_with_brand_context.return_value = {
            "content": "Response",
            "thinking": "",
        }

        # First send creates a session
        resp1 = authenticated_client_with_tenant.post(
            self.url(), {"message": "Hello"}, format="json"
        )
        assert resp1.status_code == status.HTTP_200_OK
        sid = resp1.data["session_id"]

        # Simulate an active lock on that session
        cache.add(f"chat:lock:{sid}", "1", timeout=30)

        # Second send should be rejected
        resp2 = authenticated_client_with_tenant.post(
            self.url(), {"message": "Another", "session_id": sid}, format="json"
        )
        assert resp2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # Clean up
        cache.delete(f"chat:lock:{sid}")


@pytest.mark.django_db
@pytest.mark.unit
class TestSessionListCaching:
    """Tests for session list caching per tenant."""

    def url(self):
        return reverse("chatsession-list")

    def test_list_sessions_populates_cache(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Listing sessions should populate cache."""
        from django.core.cache import cache

        cache_key = f"chat:sessions:{public_tenant.id}:" f"page=:page_size=:ordering="
        cache.delete(cache_key)

        ChatSessionFactory(tenant=public_tenant)
        response = authenticated_client_with_tenant.get(self.url())
        assert response.status_code == status.HTTP_200_OK

        cached = cache.get(cache_key)
        assert cached is not None

    def test_delete_session_invalidates_cache(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Deleting a session should invalidate cache."""
        from django.core.cache import cache

        session = ChatSessionFactory(tenant=public_tenant)
        cache_key = f"chat:sessions:{public_tenant.id}:" f"page=:page_size=:ordering="
        cache.set(cache_key, "stale-data", timeout=60)

        authenticated_client_with_tenant.delete(
            reverse("chatsession-detail", kwargs={"pk": session.pk})
        )

        cached = cache.get(cache_key)
        assert cached is None


@pytest.mark.django_db
@pytest.mark.unit
class TestSaveChatResponseToRAG:
    """Tests for save_chat_response_to_rag endpoint"""

    def url(self):
        return reverse("save_chat_response_to_rag")

    def test_unauthenticated_request_rejected(self, api_client):
        response = api_client.post(self.url(), {"content": "Hello"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_content_field(self, authenticated_client_with_tenant):
        response = authenticated_client_with_tenant.post(
            self.url(), {"title": "Test"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_title_field(self, authenticated_client_with_tenant):
        response = authenticated_client_with_tenant.post(
            self.url(), {"content": "Hello"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_company_returns_400(self, authenticated_client_with_tenant):
        response = authenticated_client_with_tenant.post(
            self.url(),
            {"content": "Hello", "title": "Test Title"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "company" in response.data["error"].lower()

    @patch("files.services.gcs_service")
    def test_save_content_success(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        from onboarding.models import BrandAsset

        mock_gcs.get_bucket.return_value = MagicMock()

        CompanyFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.post(
            self.url(),
            {
                "content": "This is important brand knowledge.",
                "title": "Brand Insight",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert "asset_id" in response.data
        assert response.data["pipeline_status"] == "pending"
        assert response.data["file_name"].startswith("brand-insight-")
        assert response.data["file_name"].endswith(".pdf")

        # Verify BrandAsset was created
        asset = BrandAsset.objects.get(id=response.data["asset_id"])
        assert asset.tenant == public_tenant
        assert asset.file_type == "document"
        mock_gcs.upload_file.assert_called_once()

        # Verify PDF content type was used
        call_args = mock_gcs.upload_file.call_args
        assert call_args[0][2] == "application/pdf"

    @patch("files.services.gcs_service")
    def test_save_content_with_title(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        mock_gcs.get_bucket.return_value = MagicMock()
        CompanyFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"content": "Some AI response text.", "title": "Blog Post"},
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["file_name"].startswith("blog-post-")
        assert response.data["file_name"].endswith(".pdf")

    @patch("files.services.gcs_service")
    def test_gcs_failure_returns_500(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        mock_gcs.get_bucket.return_value = MagicMock()
        mock_gcs.upload_file.side_effect = Exception("GCS down")
        CompanyFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"content": "Test content", "title": "Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @patch("files.services.gcs_service")
    def test_gcs_not_configured_returns_503(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        mock_gcs.get_bucket.return_value = None
        CompanyFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.post(
            self.url(),
            {"content": "Test content", "title": "Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "storage" in response.data["error"].lower()

    @patch("files.services.gcs_service")
    def test_duplicate_content_updates_existing_asset(
        self,
        mock_gcs,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        from onboarding.models import BrandAsset

        mock_gcs.get_bucket.return_value = MagicMock()
        CompanyFactory(tenant=public_tenant)

        content = "Exact same content for dedup test."
        payload = {"content": content, "title": "Dedup Test"}

        resp1 = authenticated_client_with_tenant.post(
            self.url(), payload, format="json"
        )
        resp2 = authenticated_client_with_tenant.post(
            self.url(), payload, format="json"
        )

        assert resp1.status_code == status.HTTP_202_ACCEPTED
        assert resp2.status_code == status.HTTP_202_ACCEPTED
        # Same content hash → same file_name → update_or_create reuses the asset
        assert resp1.data["file_name"] == resp2.data["file_name"]
        assert resp1.data["file_name"].endswith(".pdf")
        assert BrandAsset.objects.filter(file_name=resp1.data["file_name"]).count() == 1


@pytest.mark.django_db
@pytest.mark.unit
class TestSpeechToText:
    """Tests for the POST /api/v1/ai/speech-to-text/ endpoint."""

    URL = "/api/v1/ai/speech-to-text/"

    def test_unauthenticated_rejected(self, api_client):
        resp = api_client.post(self.URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_audio_file(self, authenticated_client_with_tenant):
        resp = authenticated_client_with_tenant.post(self.URL)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "No audio file" in resp.data["error"]

    def test_unsupported_audio_type(self, authenticated_client_with_tenant):
        from django.core.files.uploadedfile import SimpleUploadedFile

        audio = SimpleUploadedFile("test.txt", b"data", content_type="text/plain")
        resp = authenticated_client_with_tenant.post(
            self.URL, {"audio": audio}, format="multipart"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_audio_too_large(self, authenticated_client_with_tenant):
        from django.core.files.uploadedfile import SimpleUploadedFile

        large = SimpleUploadedFile(
            "big.webm", b"x" * (11 * 1024 * 1024), content_type="audio/webm"
        )
        resp = authenticated_client_with_tenant.post(
            self.URL, {"audio": large}, format="multipart"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ai_services.views.ai_service")
    def test_ai_service_not_configured(
        self, mock_svc, authenticated_client_with_tenant
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        mock_svc.model = None
        audio = SimpleUploadedFile("r.webm", b"audio", content_type="audio/webm")
        resp = authenticated_client_with_tenant.post(
            self.URL, {"audio": audio}, format="multipart"
        )
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("ai_services.views.ai_service")
    def test_successful_transcription(self, mock_svc, authenticated_client_with_tenant):
        from django.core.files.uploadedfile import SimpleUploadedFile

        mock_resp = MagicMock()
        mock_resp.text = "Hello world"
        mock_svc.model.generate_content.return_value = mock_resp

        audio = SimpleUploadedFile("r.webm", b"audio", content_type="audio/webm")
        resp = authenticated_client_with_tenant.post(
            self.URL, {"audio": audio}, format="multipart"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["transcript"] == "Hello world"

    @patch("ai_services.views.ai_service")
    def test_transcription_failure(self, mock_svc, authenticated_client_with_tenant):
        from django.core.files.uploadedfile import SimpleUploadedFile

        mock_svc.model.generate_content.side_effect = Exception("API error")
        audio = SimpleUploadedFile("r.webm", b"audio", content_type="audio/webm")
        resp = authenticated_client_with_tenant.post(
            self.URL, {"audio": audio}, format="multipart"
        )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
