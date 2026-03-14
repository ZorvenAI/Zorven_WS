"""SKL-TCIA-11: Trend Report Persister.

Persists trend reports to GCS, indexes in RAG, updates registry,
emits alerts to Kafka, and sends push notifications.
"""

import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class TrendReportPersister(BaseSkill):
    """Persist trend reports to GCS, RAG, and emit alerts."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-11",
        name="trend_report_persister",
        description="Persist trend reports to GCS, RAG, and emit alerts",
        allowed_roles=["OWNER", "ADMIN"],
        idempotent=True,
        timeout_ms=60000,
        circuit_breaker_dependency="gcs",
    )

    def __init__(
        self,
        gcs_client: Any,
        rag_service_url: str = "",
        redis_manager: Any = None,
        alert_producer: Any = None,
        core_api_url: str = "",
        core_api_token: str = "",
        circuit_breakers: dict[str, Any] | None = None,
    ) -> None:
        self._gcs = gcs_client
        self._rag_url = rag_service_url
        self._redis = redis_manager
        self._alert_producer = alert_producer
        self._core_api_url = core_api_url
        self._core_api_token = core_api_token
        self._cbs = circuit_breakers or {}

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()
        tenant_id = input_data.get("tenant_id", context.tenant_id)
        report = input_data.get("report", {})
        scored_trends = input_data.get("scored_trends", [])
        alerts = input_data.get("alerts", [])

        result_data: dict[str, Any] = {
            "report_url": "",
            "indexed_count": 0,
            "registry_updated": False,
            "alerts_emitted": 0,
            "push_notifications_sent": 0,
        }

        # 1. Upload report to GCS
        try:
            report_url = await self._gcs.upload_report(
                tenant_id,
                {"report": report, "scored_trends": scored_trends},
                report_type=report.get("report_type", "on_demand"),
            )
            result_data["report_url"] = report_url
        except Exception as exc:
            logger.warning("GCS upload failed: %s", exc)

        # 2. Index in RAG
        if self._rag_url and report.get("executive_summary"):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0)
                ) as client:
                    await client.post(
                        f"{self._rag_url}/v1/index",
                        json={
                            "content": report.get("executive_summary", ""),
                            "metadata": {
                                "type": "trend_report",
                                "tenant_id": tenant_id,
                            },
                        },
                    )
                    result_data["indexed_count"] = 1
            except Exception as exc:
                logger.warning("RAG indexing failed: %s", exc)

        # 3. Registry update is handled by TrendAnalyzer
        result_data["registry_updated"] = True

        # 4. Emit alerts via Kafka
        for alert in alerts:
            try:
                if self._alert_producer:
                    await self._alert_producer.send_alert(tenant_id, alert)
                    result_data["alerts_emitted"] += 1
            except Exception as exc:
                logger.warning("Alert emission failed: %s", exc)

        # 5. Push notifications via Django core API
        for alert in alerts:
            try:
                await self._send_push_notification(tenant_id, alert)
                result_data["push_notifications_sent"] += 1
            except Exception as exc:
                logger.warning("Push notification failed: %s", exc)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data=result_data,
            duration_ms=elapsed,
        )

    async def _send_push_notification(
        self, tenant_id: str, alert: dict[str, Any]
    ) -> None:
        """Send push notification to Django core API."""
        if not self._core_api_url:
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            await client.post(
                f"{self._core_api_url}/api/v1/orchestration/notifications/push/",
                json={
                    "notification_type": "opportunity_alert",
                    "title": f"Trend Alert: {alert.get('trend_slug', '')}",
                    "body": alert.get("recommendation", ""),
                    "metadata": alert,
                },
                headers={
                    "X-Service-Token": self._core_api_token,
                    "X-Tenant-ID": tenant_id,
                },
            )
