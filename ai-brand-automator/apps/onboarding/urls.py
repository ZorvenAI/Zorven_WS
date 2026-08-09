"""Routes for the session API, mounted at /api/v1/onboarding/.

Note there are now three things called "onboarding": the original
``onboarding`` app (mounted at ``/api/v1/`` and owning companies, assets and
progress), this app — ``apps.onboarding``, whose Django label is
``onboarding_sessions`` — and this URL prefix. The prefix was free because
the original app is mounted at the root rather than under its own name.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.onboarding.views import (
    FieldProvenanceViewSet,
    MeetingRecordingViewSet,
    OnboardingSessionViewSet,
    QuestionnaireViewSet,
    ResearchBriefViewSet,
    create_questionnaire,
    field_vocabulary,
    live_precheck,
    upsert_research_brief,
)

router = DefaultRouter()
router.register(r"sessions", OnboardingSessionViewSet, basename="onboarding-session")
router.register(r"provenance", FieldProvenanceViewSet, basename="onboarding-provenance")
router.register(r"recordings", MeetingRecordingViewSet, basename="onboarding-recording")
router.register(
    r"research-briefs", ResearchBriefViewSet, basename="onboarding-research-brief"
)
router.register(
    r"questionnaires", QuestionnaireViewSet, basename="onboarding-questionnaire"
)

urlpatterns = [
    # Before the router: a bare "research-briefs/upsert/" would otherwise
    # be read as a detail route with pk='upsert'.
    path(
        "research-briefs/upsert/",
        upsert_research_brief,
        name="onboarding-research-brief-upsert",
    ),
    path(
        "questionnaires/generate/",
        create_questionnaire,
        name="onboarding-questionnaire-generate",
    ),
    path(
        "field-vocabulary/",
        field_vocabulary,
        name="onboarding-field-vocabulary",
    ),
    path(
        "sessions/<pk>/live-precheck/",
        live_precheck,
        name="onboarding-live-precheck",
    ),
    path("", include(router.urls)),
]
