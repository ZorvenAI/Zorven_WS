from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ChatSessionViewSet,
    AIGenerationViewSet,
    chat_with_ai,
    upload_chat_attachment,
    generate_brand_strategy,
    generate_brand_identity,
    analyze_market,
)

router = DefaultRouter()
router.register(r"chat-sessions", ChatSessionViewSet)
router.register(r"generations", AIGenerationViewSet)

urlpatterns = router.urls + [
    path("chat/", chat_with_ai, name="chat_with_ai"),
    path("chat/upload/", upload_chat_attachment, name="upload_chat_attachment"),
    path(
        "generate/brand-strategy/",
        generate_brand_strategy,
        name="generate_brand_strategy",
    ),
    path(
        "generate/brand-identity/",
        generate_brand_identity,
        name="generate_brand_identity",
    ),
    path("analyze/market/", analyze_market, name="analyze_market"),
]
