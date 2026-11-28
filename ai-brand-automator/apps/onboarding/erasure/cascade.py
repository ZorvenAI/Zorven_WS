"""M-02 · GDPR erasure cascade orchestrator.

Design §20, FR-GDPR-04. Iterates registered stores in a fixed order,
calling collect() then erase() on each. Continues on individual store
failure so one broken dependency does not block the rest.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.onboarding.erasure.registry import (
    CompletionReport,
    StoreRegistry,
    StoreResult,
)

logger = logging.getLogger(__name__)

STORE_ORDER = [
    "gcs_storage",
    "brand_assets",
    "oia_redis",
    "poi_golden",
    "rag_index",
    "django_sessions",
]


class ErasureCascade:
    """Orchestrates the full GDPR erasure for one subject within one tenant."""

    def execute(
        self,
        tenant_id: str,
        subject_name: str,
        requested_by: str = "system",
        reason: str = "",
    ) -> CompletionReport:
        from django.db.models import Q

        from apps.onboarding.models import ConsentRecord

        StoreRegistry.validate_completeness()

        self._validate_store_order()

        records = ConsentRecord.objects.filter(
            Q(tenant_id=tenant_id) | Q(tenant__isnull=True),
            subject_name=subject_name,
        ).select_related("session")

        session_ids = list(records.values_list("session_id", flat=True).distinct())

        # A session holding an issued meeting record is evidence of an
        # agreement, which GDPR allows keeping to establish or defend legal
        # claims (Art. 17(3)(e)). Whether that applies to this request is a
        # person's call, so the session is left untouched in every store --
        # its recordings and transcripts are what the record rests on -- and
        # listed for review rather than erased.
        held = _sessions_with_signed_records(session_ids)
        session_ids = [sid for sid in session_ids if sid not in held]

        if not session_ids:
            logger.info(
                "erasure_no_sessions",
                extra={
                    "tenant_id": tenant_id,
                    "subject_name": subject_name,
                },
            )
            return CompletionReport(
                tenant_id=tenant_id,
                subject_name=subject_name,
                requested_by=requested_by,
                reason=reason,
                completeness_verified=not held,
                held_for_review=_held_entries(held),
            )

        report = CompletionReport(
            tenant_id=tenant_id,
            subject_name=subject_name,
            requested_by=requested_by,
            reason=reason,
            held_for_review=_held_entries(held),
        )

        store_map: dict[str, Any] = {
            cls.store_name: cls for cls in StoreRegistry.all_stores()
        }

        for store_name in STORE_ORDER:
            store_cls = store_map.get(store_name)
            if store_cls is None:
                report.store_results.append(
                    StoreResult(
                        store_name=store_name,
                        errors=[f"store {store_name} not in registry"],
                    )
                )
                continue

            store = store_cls()
            try:
                manifest = store.collect(tenant_id, session_ids, subject_name)
                result = store.erase(manifest)
            except Exception as exc:
                logger.exception(
                    "erasure_store_failed",
                    extra={"store": store_name, "error": str(exc)},
                )
                result = StoreResult(store_name=store_name, errors=[str(exc)])

            report.store_results.append(result)

        # Not complete while anything is held: the subject's data has not
        # all been erased, and someone has to decide about the rest.
        report.completeness_verified = not held and all(
            r.ok for r in report.store_results
        )
        if held:
            logger.warning(
                "erasure_held_for_review",
                extra={
                    "tenant_id": tenant_id,
                    "sessions": sorted(str(s) for s in held),
                },
            )

        logger.info(
            "erasure_cascade_complete",
            extra=report.to_dict(),
        )
        return report

    def _validate_store_order(self) -> None:
        registered = StoreRegistry.store_names()
        ordered = frozenset(STORE_ORDER)
        if registered != ordered:
            missing_from_order = registered - ordered
            missing_from_registry = ordered - registered
            raise ValueError(
                f"STORE_ORDER / registry mismatch: "
                f"in registry but not ordered={missing_from_order}, "
                f"ordered but not registered={missing_from_registry}"
            )


def _sessions_with_signed_records(session_ids) -> dict[Any, list[str]]:
    """Sessions with any record past draft, mapped to those record numbers."""
    from apps.onboarding.records.models import FROZEN_RECORD_STATUSES, MeetingRecord

    held: dict[Any, list[str]] = {}
    for session_id, number in (
        MeetingRecord.objects.filter(
            session_id__in=session_ids, status__in=FROZEN_RECORD_STATUSES
        )
        .order_by("session_id", "record_number")
        .values_list("session_id", "record_number")
    ):
        held.setdefault(session_id, []).append(number)
    return held


def _held_entries(held: dict[Any, list[str]]) -> list[dict[str, Any]]:
    return [
        {"session_id": str(session_id), "records": numbers}
        for session_id, numbers in sorted(held.items(), key=lambda kv: str(kv[0]))
    ]
