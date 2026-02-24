"""
Unit tests for ai_services serializers.
Tests ChatSessionSerializer, AIGenerationSerializer, and request serializers.
"""

import pytest

from ai_services.serializers import (
    ChatSessionSerializer,
    ChatMessageModelSerializer,
    SessionAttachmentSerializer,
    AIGenerationSerializer,
    ChatInputSerializer,
    BrandStrategyRequestSerializer,
    BrandIdentityRequestSerializer,
    MarketAnalysisRequestSerializer,
)
from ai_services.tests.factories import (
    ChatSessionFactory,
    ChatMessageFactory,
    SessionAttachmentFactory,
    AIGenerationFactory,
)


@pytest.mark.django_db
@pytest.mark.unit
class TestChatSessionSerializer:
    """Tests for ChatSessionSerializer"""

    def test_serialize_chat_session(self, public_tenant):
        """Test serializing a chat session"""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Test Session",
            messages=[{"role": "user", "content": "Hello"}],
            context={"company": "Test Co"},
        )

        serializer = ChatSessionSerializer(session)
        data = serializer.data

        assert data["id"] == session.id
        assert data["session_id"] == session.session_id
        assert data["title"] == "Test Session"
        assert data["messages"] == [{"role": "user", "content": "Hello"}]
        assert data["context"] == {"company": "Test Co"}

    def test_read_only_fields(self, public_tenant):
        """Test that read-only fields cannot be set"""
        session = ChatSessionFactory(tenant=public_tenant)
        serializer = ChatSessionSerializer(session)

        assert "id" in serializer.Meta.read_only_fields
        assert "tenant" in serializer.Meta.read_only_fields
        assert "created_at" in serializer.Meta.read_only_fields
        assert "updated_at" in serializer.Meta.read_only_fields
        assert "last_activity" in serializer.Meta.read_only_fields

    def test_deserialize_valid_data(self, public_tenant):
        """Test deserializing valid data"""
        data = {
            "session_id": "new-session-123",
            "title": "New Session",
            "messages": [],
            "context": {},
        }

        serializer = ChatSessionSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_deserialize_with_messages(self, public_tenant):
        """Test deserializing with messages array"""
        data = {
            "session_id": "session-with-messages",
            "title": "Chat with messages",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            "context": {},
        }

        serializer = ChatSessionSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_session_id_required(self):
        """Test that session_id is required"""
        data = {
            "title": "No Session ID",
            "messages": [],
        }

        serializer = ChatSessionSerializer(data=data)
        assert not serializer.is_valid()
        assert "session_id" in serializer.errors

    def test_serializer_contains_expected_fields(self, public_tenant):
        """Test that serializer contains all expected fields"""
        session = ChatSessionFactory(tenant=public_tenant)
        serializer = ChatSessionSerializer(session)

        expected_fields = {
            "id",
            "tenant",
            "session_id",
            "title",
            "messages",
            "context",
            "created_at",
            "updated_at",
            "last_activity",
            "last_message_preview",
            "message_count",
        }
        assert set(serializer.data.keys()) == expected_fields

    def test_last_message_preview(self, public_tenant):
        """Test last_message_preview returns last message content"""
        session = ChatSessionFactory(tenant=public_tenant)
        ChatMessageFactory(session=session, role="user", content="First message")
        ChatMessageFactory(
            session=session, role="assistant", content="This is the last response"
        )

        serializer = ChatSessionSerializer(session)
        assert serializer.data["last_message_preview"] == "This is the last response"

    def test_message_count(self, public_tenant):
        """Test message_count returns number of ChatMessage records"""
        session = ChatSessionFactory(tenant=public_tenant)
        ChatMessageFactory(session=session, role="user")
        ChatMessageFactory(session=session, role="assistant")
        ChatMessageFactory(session=session, role="user")

        serializer = ChatSessionSerializer(session)
        assert serializer.data["message_count"] == 3


@pytest.mark.django_db
@pytest.mark.unit
class TestAIGenerationSerializer:
    """Tests for AIGenerationSerializer"""

    def test_serialize_ai_generation(self, public_tenant):
        """Test serializing an AI generation"""
        generation = AIGenerationFactory(
            tenant=public_tenant,
            content_type="brand_strategy",
            prompt="Create a vision",
            response="Your vision is...",
            tokens_used=100,
            processing_time=1.5,
        )

        serializer = AIGenerationSerializer(generation)
        data = serializer.data

        assert data["id"] == generation.id
        assert data["content_type"] == "brand_strategy"
        assert data["prompt"] == "Create a vision"
        assert data["response"] == "Your vision is..."
        assert data["tokens_used"] == 100
        assert data["processing_time"] == 1.5

    def test_read_only_fields(self, public_tenant):
        """Test that read-only fields are correctly defined"""
        generation = AIGenerationFactory(tenant=public_tenant)
        serializer = AIGenerationSerializer(generation)

        assert "id" in serializer.Meta.read_only_fields
        assert "tenant" in serializer.Meta.read_only_fields
        assert "created_at" in serializer.Meta.read_only_fields

    def test_serializer_contains_expected_fields(self, public_tenant):
        """Test that serializer contains all expected fields"""
        generation = AIGenerationFactory(tenant=public_tenant)
        serializer = AIGenerationSerializer(generation)

        expected_fields = {
            "id",
            "tenant",
            "content_type",
            "prompt",
            "response",
            "tokens_used",
            "model_used",
            "created_at",
            "processing_time",
        }
        assert set(serializer.data.keys()) == expected_fields

    def test_content_type_choices(self):
        """Test that content_type accepts valid choices"""
        valid_types = ["brand_strategy", "brand_identity", "content", "analysis"]
        for content_type in valid_types:
            data = {
                "content_type": content_type,
                "prompt": "Test prompt",
                "response": "Test response",
            }
            serializer = AIGenerationSerializer(data=data)
            assert (
                serializer.is_valid()
            ), f"Failed for {content_type}: {serializer.errors}"


@pytest.mark.django_db
@pytest.mark.unit
class TestChatMessageModelSerializer:
    """Tests for ChatMessageModelSerializer (ChatMessage model)"""

    def test_serialize_chat_message(self, public_tenant):
        """Test serializing a ChatMessage"""
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(
            session=session,
            role="assistant",
            content="Hello!",
            thinking="Let me think...",
            metadata={"model": "gemini-2.0"},
        )

        serializer = ChatMessageModelSerializer(msg)
        data = serializer.data

        assert data["id"] == msg.id
        assert data["role"] == "assistant"
        assert data["content"] == "Hello!"
        assert data["thinking"] == "Let me think..."
        assert data["metadata"] == {"model": "gemini-2.0"}
        assert "created_at" in data

    def test_expected_fields(self, public_tenant):
        """Test serializer contains expected fields"""
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(session=session)
        serializer = ChatMessageModelSerializer(msg)

        expected = {
            "id",
            "role",
            "content",
            "metadata",
            "thinking",
            "created_at",
            "attachments",
        }
        assert set(serializer.data.keys()) == expected

    def test_attachments_included(self, public_tenant):
        """Test that attachments are included in serialized output"""
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(session=session, role="user")
        SessionAttachmentFactory(message=msg, file_name="doc.pdf")
        SessionAttachmentFactory(message=msg, file_name="img.png")

        serializer = ChatMessageModelSerializer(msg)
        assert len(serializer.data["attachments"]) == 2
        names = {a["file_name"] for a in serializer.data["attachments"]}
        assert names == {"doc.pdf", "img.png"}


@pytest.mark.django_db
@pytest.mark.unit
class TestSessionAttachmentSerializer:
    """Tests for SessionAttachmentSerializer"""

    def test_serialize_attachment(self, public_tenant):
        """Test serializing a session attachment"""
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(session=session)
        att = SessionAttachmentFactory(
            message=msg,
            file_name="report.pdf",
            file_type="document",
            file_size=2048,
            pipeline_status="indexed",
        )

        serializer = SessionAttachmentSerializer(att)
        data = serializer.data

        assert data["id"] == att.id
        assert data["file_name"] == "report.pdf"
        assert data["file_type"] == "document"
        assert data["file_size"] == 2048
        assert data["pipeline_status"] == "indexed"
        assert "created_at" in data

    def test_expected_fields(self, public_tenant):
        """Test serializer contains expected fields"""
        session = ChatSessionFactory(tenant=public_tenant)
        msg = ChatMessageFactory(session=session)
        att = SessionAttachmentFactory(message=msg)
        serializer = SessionAttachmentSerializer(att)

        expected = {
            "id",
            "message",
            "asset",
            "file_name",
            "file_type",
            "file_size",
            "pipeline_status",
            "created_at",
        }
        assert set(serializer.data.keys()) == expected


@pytest.mark.django_db
@pytest.mark.unit
class TestChatInputSerializer:
    """Tests for ChatInputSerializer (chat input)"""

    def test_valid_message(self):
        """Test valid message data"""
        data = {"message": "Hello, AI!"}
        serializer = ChatInputSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["message"] == "Hello, AI!"

    def test_message_required(self):
        """Test that message is required"""
        data = {}
        serializer = ChatInputSerializer(data=data)
        assert not serializer.is_valid()
        assert "message" in serializer.errors

    def test_empty_message_invalid(self):
        """Test that empty message is invalid"""
        data = {"message": ""}
        serializer = ChatInputSerializer(data=data)
        assert not serializer.is_valid()

    def test_message_with_session_id(self):
        """Test message with optional session_id"""
        data = {
            "message": "Hello",
            "session_id": "existing-session-123",
        }
        serializer = ChatInputSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["session_id"] == "existing-session-123"

    def test_session_id_optional(self):
        """Test that session_id is optional"""
        data = {"message": "Hello"}
        serializer = ChatInputSerializer(data=data)
        assert serializer.is_valid()

    def test_session_id_can_be_blank(self):
        """Test that session_id can be blank"""
        data = {"message": "Hello", "session_id": ""}
        serializer = ChatInputSerializer(data=data)
        assert serializer.is_valid()


@pytest.mark.django_db
@pytest.mark.unit
class TestBrandStrategyRequestSerializer:
    """Tests for BrandStrategyRequestSerializer"""

    def test_valid_request(self):
        """Test valid brand strategy request"""
        data = {"company_id": 1}
        serializer = BrandStrategyRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_company_id_required(self):
        """Test that company_id is required"""
        data = {}
        serializer = BrandStrategyRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "company_id" in serializer.errors

    def test_company_id_must_be_integer(self):
        """Test that company_id must be an integer"""
        data = {"company_id": "not-an-integer"}
        serializer = BrandStrategyRequestSerializer(data=data)
        assert not serializer.is_valid()


@pytest.mark.django_db
@pytest.mark.unit
class TestBrandIdentityRequestSerializer:
    """Tests for BrandIdentityRequestSerializer"""

    def test_valid_request(self):
        """Test valid brand identity request"""
        data = {"company_id": 1}
        serializer = BrandIdentityRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_company_id_required(self):
        """Test that company_id is required"""
        data = {}
        serializer = BrandIdentityRequestSerializer(data=data)
        assert not serializer.is_valid()


@pytest.mark.django_db
@pytest.mark.unit
class TestMarketAnalysisRequestSerializer:
    """Tests for MarketAnalysisRequestSerializer"""

    def test_valid_request(self):
        """Test valid market analysis request"""
        data = {"company_id": 1}
        serializer = MarketAnalysisRequestSerializer(data=data)
        assert serializer.is_valid()

    def test_company_id_required(self):
        """Test that company_id is required"""
        data = {}
        serializer = MarketAnalysisRequestSerializer(data=data)
        assert not serializer.is_valid()
