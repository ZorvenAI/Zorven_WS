"""Routes for the session API, mounted at /api/v1/onboarding/.

Note there are now three things called "onboarding": the original
``onboarding`` app (mounted at ``/api/v1/`` and owning companies, assets and
progress), this app — ``apps.onboarding``, whose Django label is
``onboarding_sessions`` — and this URL prefix. The prefix was free because
the original app is mounted at the root rather than under its own name.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.onboarding.erasure.views import ErasureLogListView, ErasureRequestView
from apps.onboarding.views import (
    FieldProvenanceViewSet,
    MeetingRecordingViewSet,
    OnboardingSessionViewSet,
    QuestionnaireViewSet,
    ScheduledMeetingViewSet,
    ResearchBriefViewSet,
    create_provenance_bulk,
    create_questionnaire,
    field_vocabulary,
    get_session_provenance,
    internal_generate_brand_identity,
    internal_generate_brand_strategy,
    live_precheck,
    patch_company_fields,
    patch_session_prompt_versions,
    process_callback,
    session_evidence,
    update_recording_summary,
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
# §10.2 writes this as /calendar/events/; mounted under /onboarding/ with
# the rest of the app.
router.register(
    r"calendar/events", ScheduledMeetingViewSet, basename="onboarding-calendar-event"
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
    # I-02: OIA writes summary results back via X-Service-Token auth.
    path(
        "internal/recordings/<pk>/summary/",
        update_recording_summary,
        name="onboarding-recording-summary-update",
    ),
    # J-01: OIA calls back when PROCESS completes.
    path(
        "internal/sessions/<pk>/process/callback/",
        process_callback,
        name="onboarding-process-callback",
    ),
    # L-03: OIA persists prompt versions at LIVE session end.
    path(
        "internal/sessions/<pk>/prompt-versions/",
        patch_session_prompt_versions,
        name="onboarding-session-prompt-versions",
    ),
    # J-02: OIA fetches the evidence bundle for a session.
    path(
        "internal/sessions/<pk>/evidence/",
        session_evidence,
        name="onboarding-session-evidence",
    ),
    # J-03: OIA writes extracted Company fields back.
    path(
        "internal/companies/<pk>/fields/",
        patch_company_fields,
        name="onboarding-company-fields-patch",
    ),
    # J-03: OIA bulk-creates FieldProvenance records.
    path(
        "internal/sessions/<pk>/provenance/bulk/",
        create_provenance_bulk,
        name="onboarding-provenance-bulk-create",
    ),
    # J-03: OIA reads existing FieldProvenance for PG-06 checks.
    path(
        "internal/sessions/<pk>/provenance/",
        get_session_provenance,
        name="onboarding-session-provenance",
    ),
    # J-06: OIA triggers brand strategy generation (SKL-OIA-12).
    path(
        "internal/companies/<int:pk>/generate-strategy/",
        internal_generate_brand_strategy,
        name="onboarding-internal-generate-strategy",
    ),
    # J-06: OIA triggers brand identity generation (SKL-OIA-12).
    path(
        "internal/companies/<int:pk>/generate-identity/",
        internal_generate_brand_identity,
        name="onboarding-internal-generate-identity",
    ),
    path(
        "erasure/",
        ErasureRequestView.as_view(),
        name="onboarding-erasure-request",
    ),
    path(
        "erasure/logs/",
        ErasureLogListView.as_view(),
        name="onboarding-erasure-logs",
    ),
    path("", include(router.urls)),
]
