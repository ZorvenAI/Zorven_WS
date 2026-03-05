"""
Unit Tests for DbSyncService.

Tests document builders for each syncable model, document ID generation,
tenant ID extraction, and eligibility filtering.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rag_index.services.db_sync_service import DbSyncService

# ============================================================================
# Fixtures — lightweight model stubs (no Django ORM needed)
# ============================================================================


@pytest.fixture
def db_sync():
    return DbSyncService()


@pytest.fixture
def company_stub():
    """Stub Company with all text fields."""
    assets = MagicMock()
    assets.count.return_value = 3
    return SimpleNamespace(
        id=42,
        pk=42,
        name="Acme Corp",
        description="A tech company building AI tools",
        industry="Technology",
        website="https://acme.example.com",
        target_audience="Startups and SMBs",
        core_problem="Manual brand building is slow",
        demographics="Ages 25-45, urban professionals",
        psychographics="Innovation-oriented, tech-savvy",
        pain_points="Time-consuming brand development",
        desired_outcomes="Automated brand strategy",
        brand_voice="professional",
        vision_statement="AI for every brand",
        mission_statement="We make branding accessible",
        values="Innovation, Quality, Speed",
        positioning_statement="The fastest AI brand builder",
        tagline="Build your brand, faster",
        value_proposition="10x faster brand creation",
        elevator_pitch="We help startups build brands in hours, not months",
        color_palette_desc="Deep blue, electric cyan, silver accents",
        font_recommendations="Inter for headings, Source Sans for body",
        messaging_guide="Professional yet approachable tone",
        created_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        tenant=SimpleNamespace(id=7),
        assets=assets,
    )


@pytest.fixture
def analysis_job_stub():
    """Stub completed AnalysisJob."""
    return SimpleNamespace(
        id=99,
        pk=99,
        job_id="aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        input_prompt="Analyse brand equity for Acme Corp",
        result_data={"score": 85, "dimensions": {"awareness": 90}},
        status="completed",
        error_message="",
        duration_seconds=12.5,
        created_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
        completed_at=datetime(2025, 3, 1, 0, 0, 13, tzinfo=timezone.utc),
        updated_at=datetime(2025, 3, 1, 0, 0, 13, tzinfo=timezone.utc),
        tenant=SimpleNamespace(id=7),
    )


@pytest.fixture
def chat_message_stub():
    """Stub assistant ChatMessage."""
    return SimpleNamespace(
        id=500,
        pk=500,
        role="assistant",
        content="Based on your brand strategy, I recommend focusing on...",
        session_id=10,
        session=SimpleNamespace(
            title="Brand Strategy Session",
            tenant=SimpleNamespace(id=7),
        ),
        created_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def ai_generation_stub():
    """Stub AIGeneration."""
    return SimpleNamespace(
        id=200,
        pk=200,
        content_type="brand_strategy",
        prompt="Generate a brand strategy for a tech startup",
        response="Here is a comprehensive brand strategy...",
        model_used="gemini-2.0-flash-exp",
        tokens_used=1500,
        created_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
        tenant=SimpleNamespace(id=7),
    )


@pytest.fixture
def content_calendar_stub():
    """Stub published ContentCalendar."""
    return SimpleNamespace(
        id=300,
        pk=300,
        title="Launch announcement post",
        content="We're excited to announce our new AI-powered brand tool!",
        platforms=["linkedin", "twitter"],
        status="published",
        scheduled_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        published_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=datetime(2025, 5, 28, tzinfo=timezone.utc),
        updated_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
        tenant=SimpleNamespace(id=7),
    )


# ============================================================================
# Document ID tests
# ============================================================================


class TestGetDocumentId:
    def test_company_id(self, db_sync, company_stub):
        assert db_sync.get_document_id("Company", company_stub) == "company-42"

    def test_analysis_job_id_uses_job_id(self, db_sync, analysis_job_stub):
        doc_id = db_sync.get_document_id("AnalysisJob", analysis_job_stub)
        assert doc_id == f"analysis-{analysis_job_stub.job_id}"

    def test_chat_message_id(self, db_sync, chat_message_stub):
        assert (
            db_sync.get_document_id("ChatMessage", chat_message_stub) == "chat-msg-500"
        )

    def test_ai_generation_id(self, db_sync, ai_generation_stub):
        assert (
            db_sync.get_document_id("AIGeneration", ai_generation_stub) == "ai-gen-200"
        )

    def test_content_calendar_id(self, db_sync, content_calendar_stub):
        assert (
            db_sync.get_document_id("ContentCalendar", content_calendar_stub)
            == "content-cal-300"
        )


# ============================================================================
# Tenant ID extraction tests
# ============================================================================


class TestGetTenantId:
    def test_direct_tenant(self, db_sync, company_stub):
        assert db_sync.get_tenant_id(company_stub) == "7"

    def test_session_tenant(self, db_sync, chat_message_stub):
        assert db_sync.get_tenant_id(chat_message_stub) == "7"

    def test_no_tenant(self, db_sync):
        obj = SimpleNamespace(id=1, pk=1)
        assert db_sync.get_tenant_id(obj) is None


# ============================================================================
# Should Sync (eligibility) tests
# ============================================================================


class TestShouldSync:
    def test_company_always(self, db_sync, company_stub):
        assert db_sync.should_sync("Company", company_stub) is True

    def test_analysis_job_completed(self, db_sync, analysis_job_stub):
        assert db_sync.should_sync("AnalysisJob", analysis_job_stub) is True

    def test_analysis_job_running(self, db_sync):
        job = SimpleNamespace(status="running")
        assert db_sync.should_sync("AnalysisJob", job) is False

    def test_chat_message_assistant(self, db_sync, chat_message_stub):
        assert db_sync.should_sync("ChatMessage", chat_message_stub) is True

    def test_chat_message_user(self, db_sync):
        msg = SimpleNamespace(role="user")
        assert db_sync.should_sync("ChatMessage", msg) is False

    def test_content_calendar_published(self, db_sync, content_calendar_stub):
        assert db_sync.should_sync("ContentCalendar", content_calendar_stub) is True

    def test_content_calendar_draft(self, db_sync):
        post = SimpleNamespace(status="draft")
        assert db_sync.should_sync("ContentCalendar", post) is False


# ============================================================================
# Company document builder tests
# ============================================================================


class TestBuildCompanyDoc:
    def test_document_type(self, db_sync, company_stub):
        doc = db_sync.build_document("Company", company_stub)
        assert doc["document_type"] == "company_profile"

    def test_metadata_fields(self, db_sync, company_stub):
        doc = db_sync.build_document("Company", company_stub)
        meta = doc["metadata"]
        assert meta["name"] == "Acme Corp"
        assert meta["industry"] == "Technology"
        assert meta["brand_voice"] == "professional"
        assert meta["company_id"] == "42"
        assert meta["created_at"] is not None
        assert meta["updated_at"] is not None

    def test_extracted_text_includes_all_fields(self, db_sync, company_stub):
        doc = db_sync.build_document("Company", company_stub)
        text = doc["extracted_text"]
        assert "Acme Corp" in text
        assert "tech company" in text
        assert "Technology" in text
        assert "Startups and SMBs" in text
        assert "Manual brand building" in text
        assert "professional" in text
        assert "AI for every brand" in text
        assert "Innovation, Quality, Speed" in text
        assert "Build your brand, faster" in text
        assert "Deep blue" in text
        assert "Inter for headings" in text
        assert "Professional yet approachable" in text
        assert "3 files uploaded" in text

    def test_empty_fields_skipped(self, db_sync):
        company = SimpleNamespace(
            id=1,
            pk=1,
            name="Test",
            description="",
            industry="",
            website="",
            target_audience="",
            core_problem="",
            demographics="",
            psychographics="",
            pain_points="",
            desired_outcomes="",
            brand_voice="",
            vision_statement="",
            mission_statement="",
            values="",
            positioning_statement="",
            tagline="",
            value_proposition="",
            elevator_pitch="",
            color_palette_desc="",
            font_recommendations="",
            messaging_guide="",
            created_at=None,
            updated_at=None,
            tenant=None,
            assets=MagicMock(**{"count.return_value": 0}),
        )
        doc = db_sync.build_document("Company", company)
        assert "Company: Test" in doc["extracted_text"]
        # Should not have empty labels
        assert "Description: \n" not in doc["extracted_text"]


# ============================================================================
# AnalysisJob document builder tests
# ============================================================================


class TestBuildAnalysisJobDoc:
    def test_document_type(self, db_sync, analysis_job_stub):
        doc = db_sync.build_document("AnalysisJob", analysis_job_stub)
        assert doc["document_type"] == "analysis_job"

    def test_metadata(self, db_sync, analysis_job_stub):
        doc = db_sync.build_document("AnalysisJob", analysis_job_stub)
        meta = doc["metadata"]
        assert meta["job_id"] == str(analysis_job_stub.job_id)
        assert meta["status"] == "completed"
        assert meta["duration_seconds"] == 12.5

    def test_extracted_text_contains_prompt_and_results(
        self, db_sync, analysis_job_stub
    ):
        doc = db_sync.build_document("AnalysisJob", analysis_job_stub)
        text = doc["extracted_text"]
        assert "Analyse brand equity" in text
        assert '"score": 85' in text


# ============================================================================
# ChatMessage document builder tests
# ============================================================================


class TestBuildChatMessageDoc:
    def test_document_type(self, db_sync, chat_message_stub):
        doc = db_sync.build_document("ChatMessage", chat_message_stub)
        assert doc["document_type"] == "chat_message"

    def test_includes_session_title(self, db_sync, chat_message_stub):
        doc = db_sync.build_document("ChatMessage", chat_message_stub)
        assert "Brand Strategy Session" in doc["extracted_text"]

    def test_metadata(self, db_sync, chat_message_stub):
        doc = db_sync.build_document("ChatMessage", chat_message_stub)
        assert doc["metadata"]["role"] == "assistant"
        assert doc["metadata"]["session_id"] == "10"


# ============================================================================
# AIGeneration document builder tests
# ============================================================================


class TestBuildAIGenerationDoc:
    def test_document_type(self, db_sync, ai_generation_stub):
        doc = db_sync.build_document("AIGeneration", ai_generation_stub)
        assert doc["document_type"] == "ai_generation"

    def test_metadata(self, db_sync, ai_generation_stub):
        doc = db_sync.build_document("AIGeneration", ai_generation_stub)
        meta = doc["metadata"]
        assert meta["content_type"] == "brand_strategy"
        assert meta["model_used"] == "gemini-2.0-flash-exp"
        assert meta["tokens_used"] == 1500

    def test_extracted_text(self, db_sync, ai_generation_stub):
        doc = db_sync.build_document("AIGeneration", ai_generation_stub)
        text = doc["extracted_text"]
        assert "brand_strategy" in text
        assert "Generate a brand strategy" in text
        assert "comprehensive brand strategy" in text


# ============================================================================
# ContentCalendar document builder tests
# ============================================================================


class TestBuildContentCalendarDoc:
    def test_document_type(self, db_sync, content_calendar_stub):
        doc = db_sync.build_document("ContentCalendar", content_calendar_stub)
        assert doc["document_type"] == "content_calendar"

    def test_metadata(self, db_sync, content_calendar_stub):
        doc = db_sync.build_document("ContentCalendar", content_calendar_stub)
        meta = doc["metadata"]
        assert meta["title"] == "Launch announcement post"
        assert meta["platforms"] == ["linkedin", "twitter"]
        assert meta["status"] == "published"

    def test_extracted_text(self, db_sync, content_calendar_stub):
        doc = db_sync.build_document("ContentCalendar", content_calendar_stub)
        text = doc["extracted_text"]
        assert "Launch announcement" in text
        assert "AI-powered brand tool" in text
        assert "linkedin" in text


# ============================================================================
# Unknown model tests
# ============================================================================


class TestUnknownModel:
    def test_build_document_returns_none(self, db_sync):
        result = db_sync.build_document("UnknownModel", SimpleNamespace(id=1))
        assert result is None

    def test_get_model_class_raises(self, db_sync):
        with pytest.raises(ValueError, match="Unknown syncable model"):
            db_sync.get_model_class("UnknownModel")
