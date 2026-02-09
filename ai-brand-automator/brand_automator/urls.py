"""
URL configuration for brand_automator project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from brand_automator.auth_views import (
    EmailTokenObtainPairView,
    UserRegistrationView,
    EmailVerificationView,
    PasswordResetRequestView,
)
from brand_automator.health_views import (
    HealthCheckView,
    ReadinessCheckView,
    LivenessCheckView,
)


urlpatterns = [
    path("admin/", admin.site.urls),
    # Health check endpoints
    path("health/", HealthCheckView.as_view(), name="health_check"),
    path("ready/", ReadinessCheckView.as_view(), name="readiness_check"),
    path("alive/", LivenessCheckView.as_view(), name="liveness_check"),
    path(
        "api/v1/",
        include(
            [
                # Authentication - now accepts email instead of username
                path(
                    "auth/register/",
                    UserRegistrationView.as_view(),
                    name="user_register",
                ),
                path(
                    "auth/login/",
                    EmailTokenObtainPairView.as_view(),
                    name="token_obtain_pair",
                ),
                path(
                    "auth/refresh/",
                    TokenRefreshView.as_view(),
                    name="token_refresh",
                ),
                path(
                    "auth/verify-email/",
                    EmailVerificationView.as_view(),
                    name="email_verify",
                ),
                path(
                    "auth/password-reset/",
                    PasswordResetRequestView.as_view(),
                    name="password_reset",
                ),
                # Onboarding
                path("", include("onboarding.urls")),
                # AI Services
                path("ai/", include("ai_services.urls")),
                # Subscriptions
                path("subscriptions/", include("subscriptions.urls")),
                # Tenant management (admin only)
                path("tenants/", include("tenants.urls")),
                # Automation (LinkedIn, social media, content scheduling)
                path("automation/", include("automation.urls")),
                # Data Ingestion (file processing pipeline)
                path("ingestion/", include("data_ingestion.urls")),
                # Media Curation (AI content curation pipeline)
                path("curation/", include("media_curation.urls")),
                # RAG Index (document sync to Vertex AI)
                path("rag-index/", include("rag_index.api.urls")),
            ]
        ),
    ),
]
