"""Routes for the session API, mounted at /api/v1/onboarding/.

Note there are now three things called "onboarding": the original
``onboarding`` app (mounted at ``/api/v1/`` and owning companies, assets and
progress), this app — ``apps.onboarding``, whose Django label is
``onboarding_sessions`` — and this URL prefix. The prefix was free because
the original app is mounted at the root rather than under its own name.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.onboarding.views import OnboardingSessionViewSet

router = DefaultRouter()
router.register(r"sessions", OnboardingSessionViewSet, basename="onboarding-session")

urlpatterns = [
    path("", include(router.urls)),
]
