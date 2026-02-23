"""
Property-based tests using Hypothesis for ai_services app.
Tests invariants and edge cases through automated random data generation.
"""

import pytest
import uuid
from hypothesis import given, assume, strategies as st, settings, HealthCheck
from django.db import connection

from ai_services.models import ChatSession, AIGeneration
from ai_services.serializers import (
    ChatSessionSerializer,
    AIGenerationSerializer,
    ChatInputSerializer,
)
from ai_services.tests.factories import ChatSessionFactory, AIGenerationFactory

# Suppress health check for function-scoped fixtures
# Reduced max_examples for faster CI runs (each creates a new tenant)
property_settings = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=5,  # Reduced from 10 for performance
    deadline=None,
)


def create_test_tenant():
    """Create a unique tenant for each Hypothesis example."""
    from tenants.models import Tenant, Domain

    connection.set_schema_to_public()

    unique_id = uuid.uuid4().hex[:10]
    schema_name = f"ai_test_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"AI Test Tenant {unique_id}",
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


@pytest.mark.django_db
@pytest.mark.property
class TestChatSessionProperties:
    """Property-based tests for ChatSession model"""

    @property_settings
    @given(
        title=st.text(min_size=0, max_size=255),
        num_messages=st.integers(min_value=0, max_value=50),
    )
    def test_session_accepts_any_valid_title(self, title, num_messages):
        """Property: Any string up to 255 chars is valid for title"""
        tenant = create_test_tenant()

        session = ChatSession.objects.create(
            tenant=tenant,
            session_id=str(uuid.uuid4()),
            title=title[:255],
            messages=[],
        )

        session.refresh_from_db()
        assert session.title == title[:255]

    @property_settings
    @given(
        messages=st.lists(
            st.fixed_dictionaries(
                {
                    "role": st.sampled_from(["user", "assistant", "system"]),
                    "content": st.text(min_size=1, max_size=500),
                }
            ),
            min_size=0,
            max_size=20,
        )
    )
    def test_messages_json_field_handles_any_message_list(self, messages):
        """Property: Messages JSONField accepts any list of message dicts"""
        tenant = create_test_tenant()

        session = ChatSession.objects.create(
            tenant=tenant,
            session_id=str(uuid.uuid4()),
            messages=messages,
        )

        session.refresh_from_db()
        assert len(session.messages) == len(messages)

    @property_settings
    @given(
        context=st.fixed_dictionaries(
            {
                "company": st.text(min_size=0, max_size=100),
                "industry": st.text(min_size=0, max_size=50),
            }
        )
    )
    def test_context_json_field_handles_any_dict(self, context):
        """Property: Context JSONField accepts any dict"""
        tenant = create_test_tenant()

        session = ChatSession.objects.create(
            tenant=tenant,
            session_id=str(uuid.uuid4()),
            context=context,
        )

        session.refresh_from_db()
        assert session.context == context


@pytest.mark.django_db
@pytest.mark.property
class TestAIGenerationProperties:
    """Property-based tests for AIGeneration model"""

    @property_settings
    @given(
        prompt=st.text(min_size=1, max_size=5000),
        response=st.text(min_size=1, max_size=5000),
    )
    def test_long_prompts_and_responses_handled(self, prompt, response):
        """Property: Any text prompt/response is stored correctly"""
        assume(len(prompt.strip()) > 0)
        assume(len(response.strip()) > 0)

        tenant = create_test_tenant()

        generation = AIGeneration.objects.create(
            tenant=tenant,
            content_type="content",
            prompt=prompt,
            response=response,
        )

        generation.refresh_from_db()
        assert generation.prompt == prompt
        assert generation.response == response

    @property_settings
    @given(
        tokens=st.integers(min_value=0, max_value=1000000),
        processing_time=st.floats(min_value=0.0, max_value=300.0),
    )
    def test_tokens_and_processing_time_valid(self, tokens, processing_time):
        """Property: Any non-negative tokens and processing time are valid"""
        tenant = create_test_tenant()

        generation = AIGeneration.objects.create(
            tenant=tenant,
            content_type="brand_strategy",
            prompt="Test prompt",
            response="Test response",
            tokens_used=tokens,
            processing_time=processing_time,
        )

        generation.refresh_from_db()
        assert generation.tokens_used == tokens
        assert abs(generation.processing_time - processing_time) < 0.001


@pytest.mark.django_db
@pytest.mark.property
class TestChatInputSerializerProperties:
    """Property-based tests for ChatInputSerializer"""

    @property_settings
    @given(message=st.text(min_size=1, max_size=1000))
    def test_any_non_empty_message_is_valid(self, message):
        """Property: Any non-empty string is valid for message"""
        assume(len(message.strip()) > 0)

        serializer = ChatInputSerializer(data={"message": message})
        assert serializer.is_valid(), f"Failed for message: {repr(message)}"

    @property_settings
    @given(
        message=st.text(min_size=1, max_size=100),
        session_id=st.text(min_size=0, max_size=255),
    )
    def test_message_with_optional_session_id(self, message, session_id):
        """Property: Message serializer accepts any session_id"""
        assume(len(message.strip()) > 0)

        serializer = ChatInputSerializer(
            data={"message": message, "session_id": session_id}
        )
        assert serializer.is_valid()


@pytest.mark.django_db
@pytest.mark.property
class TestSerializerRoundtripProperties:
    """Property-based tests for serializer round-trips"""

    @property_settings
    @given(
        title=st.text(min_size=0, max_size=200),
    )
    def test_chat_session_serializer_roundtrip(self, title):
        """Property: ChatSession serializes and deserializes correctly"""
        tenant = create_test_tenant()

        session = ChatSessionFactory(tenant=tenant, title=title[:200])
        serializer = ChatSessionSerializer(session)
        data = serializer.data

        # Key fields should be present
        assert "id" in data
        assert "session_id" in data
        assert data["title"] == title[:200]

    @property_settings
    @given(
        content_type=st.sampled_from(
            ["brand_strategy", "brand_identity", "content", "analysis"]
        ),
        tokens=st.integers(min_value=0, max_value=10000),
    )
    def test_ai_generation_serializer_roundtrip(self, content_type, tokens):
        """Property: AIGeneration serializes correctly"""
        tenant = create_test_tenant()

        generation = AIGenerationFactory(
            tenant=tenant,
            content_type=content_type,
            tokens_used=tokens,
        )
        serializer = AIGenerationSerializer(generation)
        data = serializer.data

        assert data["content_type"] == content_type
        assert data["tokens_used"] == tokens


@pytest.mark.django_db
@pytest.mark.property
class TestAddMessageInvariants:
    """Property-based tests for ChatSession.add_message invariants"""

    @property_settings
    @given(
        role=st.sampled_from(["user", "assistant", "system"]),
        content=st.text(min_size=1, max_size=500),
    )
    def test_add_message_always_increases_count(self, role, content):
        """Property: add_message always increases message count by 1"""
        assume(len(content.strip()) > 0)

        tenant = create_test_tenant()
        session = ChatSessionFactory(tenant=tenant, messages=[])

        initial_count = len(session.messages)
        session.add_message(role, content)

        assert len(session.messages) == initial_count + 1

    @property_settings
    @given(
        messages=st.lists(
            st.tuples(
                st.sampled_from(["user", "assistant"]),
                st.text(min_size=1, max_size=100),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_messages_order_preserved(self, messages):
        """Property: Messages are added in correct order"""
        tenant = create_test_tenant()
        session = ChatSessionFactory(tenant=tenant, messages=[])

        for role, content in messages:
            if content.strip():
                session.add_message(role, content)

        # Verify order is preserved
        for i, (role, content) in enumerate(messages):
            if content.strip() and i < len(session.messages):
                assert session.messages[i]["role"] == role
                assert session.messages[i]["content"] == content
