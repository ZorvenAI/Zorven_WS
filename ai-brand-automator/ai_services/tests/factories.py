"""
Factory Boy factories for ai_services models
"""

import factory
import uuid
from factory.django import DjangoModelFactory
from django.utils import timezone

from ai_services.models import ChatSession, ChatMessage, SessionAttachment, AIGeneration
from tenants.models import Tenant


class TenantFactory(DjangoModelFactory):
    """Factory for Tenant model (used in ai_services tests)"""

    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"AI Test Tenant {n}")
    schema_name = factory.LazyAttribute(lambda obj: f"ai_test_{uuid.uuid4().hex[:8]}")
    subscription_status = "active"
    max_users = 10
    storage_limit_gb = 5


class ChatSessionFactory(DjangoModelFactory):
    """Factory for ChatSession model"""

    class Meta:
        model = ChatSession

    tenant = factory.SubFactory(TenantFactory)
    session_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    title = factory.Faker("sentence", nb_words=4)
    messages = factory.LazyFunction(list)
    context = factory.LazyFunction(dict)
    created_at = factory.LazyFunction(timezone.now)
    last_activity = factory.LazyFunction(timezone.now)


class ChatMessageFactory(DjangoModelFactory):
    """Factory for ChatMessage model"""

    class Meta:
        model = ChatMessage

    session = factory.SubFactory(ChatSessionFactory)
    role = "user"
    content = factory.Faker("sentence", nb_words=10)
    metadata = factory.LazyFunction(dict)
    thinking = ""
    created_at = factory.LazyFunction(timezone.now)


class SessionAttachmentFactory(DjangoModelFactory):
    """Factory for SessionAttachment model"""

    class Meta:
        model = SessionAttachment

    message = factory.SubFactory(ChatMessageFactory)
    asset = None
    file_name = factory.Faker("file_name", extension="pdf")
    file_type = "document"
    file_size = factory.Faker("random_int", min=1024, max=5_000_000)
    pipeline_status = "pending"


class AIGenerationFactory(DjangoModelFactory):
    """Factory for AIGeneration model"""

    class Meta:
        model = AIGeneration

    tenant = factory.SubFactory(TenantFactory)
    content_type = factory.Faker(
        "random_element",
        elements=["brand_strategy", "brand_identity", "content", "analysis"],
    )
    prompt = factory.Faker("paragraph", nb_sentences=3)
    response = factory.Faker("paragraph", nb_sentences=5)
    tokens_used = factory.Faker("random_int", min=50, max=500)
    model_used = "gemini-1.5-flash"
    processing_time = factory.Faker("pyfloat", min_value=0.1, max_value=5.0)
