"""
Unit tests for ai_services views.
Tests ChatSessionViewSet, AIGenerationViewSet, and API endpoints.
"""

import pytest
import uuid
from unittest.mock import patch
from rest_framework import status
from django.urls import reverse

from ai_services.tests.factories import ChatSessionFactory, AIGenerationFactory
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

    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_chat_with_valid_message(
        self,
        mock_ai_service,
        mock_classify,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Test chat with valid message"""
        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai_service.chat_with_brand_context.return_value = "AI Response"

        response = authenticated_client_with_tenant.post(
            self.url(), {"message": "Hello, AI!"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert mock_ai_service.chat_with_brand_context.called
        assert response.data["pipeline_job"] is None


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

    @patch("ai_services.services.GeminiAIService.classify_intent")
    @patch("ai_services.views.ai_service")
    def test_conversational_message_no_pipeline(
        self,
        mock_ai,
        mock_classify,
        authenticated_client_with_tenant,
        public_tenant,
    ):
        """Conversational message should NOT trigger pipeline."""
        mock_classify.return_value = {"intent": "conversation", "confidence": 1.0}
        mock_ai.chat_with_brand_context.return_value = "Hello!"

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
