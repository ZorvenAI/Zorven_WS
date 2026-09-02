"""M-02 · Django session model store.

Deletes OnboardingSession rows. CASCADE handles:
MeetingRecording, ConsentRecord, FieldProvenance, ResearchBrief,
Questionnaire → Question, ScheduledMeeting → CalendarSyncConflict.
"""

from __future__ import annotations

import logging

from apps.onboarding.erasure.registry import (
    ErasureManifest,
    ErasureStore,
    StoreRegistry,
    StoreResult,
)

logger = logging.getLogger(__name__)


@StoreRegistry.register
class DjangoSessionStore(ErasureStore):
    store_name = "django_sessions"
    artifact_types = ("recordings", "provenance", "summaries")

    def collect(self, tenant_id, session_ids, subject_name):
        from apps.onboarding.models import OnboardingSession

        sessions = OnboardingSession.objects.filter(
            tenant_id=tenant_id, pk__in=session_ids
        )
        count = sessions.count()
        return ErasureManifest(
            store_name=self.store_name,
            item_count=count,
            details={"session_ids": list(sessions.values_list("pk", flat=True))},
        )

    def erase(self, manifest):
        from apps.onboarding.models import OnboardingSession

        session_ids = manifest.details.get("session_ids", [])
        if not session_ids:
            return StoreResult(store_name=self.store_name)

        deleted_count, breakdown = OnboardingSession.objects.filter(
            pk__in=session_ids
        ).delete()

        logger.info(
            "erasure_django_sessions",
            extra={"deleted": deleted_count, "breakdown": breakdown},
        )
        return StoreResult(
            store_name=self.store_name,
            items_erased=deleted_count,
            details={"cascade_breakdown": breakdown},
        )
