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
        from apps.onboarding.models import ConsentRecord

        StoreRegistry.validate_completeness()

        self._validate_store_order()

        records = ConsentRecord.objects.filter(
            tenant_id=tenant_id,
            subject_name=subject_name,
        ).select_related("session")

        session_ids = list(records.values_list("session_id", flat=True).distinct())

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
                completeness_verified=True,
            )

        report = CompletionReport(
            tenant_id=tenant_id,
            subject_name=subject_name,
            requested_by=requested_by,
            reason=reason,
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

        report.completeness_verified = all(r.ok for r in report.store_results)

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
