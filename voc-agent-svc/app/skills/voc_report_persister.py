"""SKL-VoCA-13: VoC Report Persister.

Persists VoC reports to GCS, updates the feedback registry in Redis
(themes, sentiment daily, NPS monthly, coverage score), indexes in RAG,
and emits VoC insight alerts to Kafka voc-insights-topic via AlertProducer.

Alert triggers:
- Critical negative sentiment (>60% negative)
- NPS drop >10 points
- New critical theme detected
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class VoCReportPersister(BaseSkill):
    """Persist VoC reports to GCS, update registry, and emit insight alerts."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-13",
        name="voc_report_persister",
        description=(
            "Persist VoC reports to GCS, update feedback registry in Redis "
            "(themes, sentiment daily, NPS monthly, coverage score), index "
            "in RAG, and emit VoC insight alerts to Kafka voc-insights-topic."
        ),
        allowed_roles=["OWNER", "ADMIN"],
        idempotent=False,
        timeout_ms=60000,
        circuit_breaker_dependency="gcs",
    )

    def __init__(
        self,
        gcs_enabled: bool = False,
        rag_enabled: bool = False,
        rag_service_url: str = "http://localhost:8070",
        feedback_registry: Any = None,
        alert_producer: Any = None,
    ) -> None:
        self.gcs_enabled = gcs_enabled
        self.rag_enabled = rag_enabled
        self.rag_service_url = rag_service_url
        self._registry = feedback_registry
        self._alert_producer = alert_producer
        self._gcs_client = None

    def _ensure_gcs_client(self) -> None:
        """Lazy-initialize GCS client."""
        if self._gcs_client or not self.gcs_enabled:
            return
        try:
            from app.services.gcs_client import GCSClient

            self._gcs_client = GCSClient(
                project_id="",
                bucket_name="voc-reports",
            )
        except Exception as exc:
            logger.warning("GCS client init failed: %s", exc)

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Persist VoC report data.

        input_data keys:
          - report_data (dict): Compiled VoC report data from upstream skills
          - prompt (str): Original query
          - themes (list[dict]): Extracted theme clusters
          - sentiment (dict): Sentiment breakdown {positive, negative, neutral}
          - nps_data (dict): NPS data {score, period, previous_score}
          - coverage_data (dict): Data coverage {score, channels, mode}
        """
        start = time.monotonic()

        report_data = input_data.get("report_data", {})
        prompt = input_data.get("prompt", "")
        themes = input_data.get("themes", [])
        sentiment = input_data.get("sentiment", {})
        nps_data = input_data.get("nps_data", {})
        coverage_data = input_data.get("coverage_data", {})
        tenant_id = context.tenant_id

        result_data: dict[str, Any] = {
            "report_url": "",
            "indexed_count": 0,
            "registry_updated": False,
            "insights_emitted": 0,
        }

        if not report_data:
            logger.info("No report data to persist for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        try:
            # 1. Persist report to GCS
            report_url = await self._persist_to_gcs(
                tenant_id, report_data
            )
            result_data["report_url"] = report_url

            # 2. Index in RAG
            indexed = await self._index_in_rag(
                tenant_id, prompt, report_data
            )
            result_data["indexed_count"] = indexed

            # 3. Update feedback registry in Redis
            registry_updated = await self._update_registry(
                tenant_id, themes, sentiment, nps_data, coverage_data
            )
            result_data["registry_updated"] = registry_updated

            # 4. Evaluate and emit insight alerts
            insights_emitted = await self._emit_insight_alerts(
                tenant_id, sentiment, nps_data, themes
            )
            result_data["insights_emitted"] = insights_emitted

            logger.info(
                "VoC report persisted for tenant %s: gcs=%s rag=%d "
                "registry=%s alerts=%d (%.0fms)",
                tenant_id,
                bool(report_url),
                indexed,
                registry_updated,
                insights_emitted,
                _elapsed(start),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.error(
                "VoC report persistence failed for tenant %s: %s",
                tenant_id,
                exc,
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                data=result_data,
                error=str(exc),
                duration_ms=_elapsed(start),
            )

    # ── GCS Persistence ──

    async def _persist_to_gcs(
        self, tenant_id: str, report_data: dict[str, Any]
    ) -> str:
        """Upload VoC report to GCS. Returns the GCS URI or empty string."""
        if not self.gcs_enabled:
            logger.debug("GCS disabled, skipping upload for tenant %s", tenant_id)
            return ""

        self._ensure_gcs_client()
        if not self._gcs_client:
            logger.warning("GCS client not available, skipping upload")
            return ""

        try:
            report_id = str(uuid.uuid4())
            uri = await self._gcs_client.upload_report(
                tenant_id=tenant_id,
                report_id=report_id,
                report_data=report_data,
            )
            logger.info("VoC report uploaded to GCS: %s", uri)
            return uri
        except Exception as exc:
            logger.warning("GCS upload failed for tenant %s: %s", tenant_id, exc)
            return ""

    # ── RAG Indexing ──

    async def _index_in_rag(
        self, tenant_id: str, prompt: str, report_data: dict[str, Any]
    ) -> int:
        """Index VoC report in RAG service for future retrieval."""
        if not self.rag_enabled or not self.rag_service_url:
            return 0

        try:
            url = f"{self.rag_service_url}/v1/index"
            payload = {
                "tenant_id": tenant_id,
                "content_type": "voice_of_customer",
                "content": json.dumps(report_data)[:50000],
                "metadata": {
                    "query": prompt[:500],
                    "type": "voc_report",
                },
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"X-Tenant-ID": tenant_id},
                )
                resp.raise_for_status()
            return 1
        except Exception as exc:
            logger.warning("RAG indexing failed for tenant %s: %s", tenant_id, exc)
            return 0

    # ── Feedback Registry Update ──

    async def _update_registry(
        self,
        tenant_id: str,
        themes: list[dict[str, Any]],
        sentiment: dict[str, Any],
        nps_data: dict[str, Any],
        coverage_data: dict[str, Any],
    ) -> bool:
        """Update feedback registry in Redis with themes, sentiment, NPS, coverage."""
        if not self._registry:
            return False

        updated = False

        # Update theme clusters
        try:
            for theme in themes:
                theme_slug = theme.get("slug", "")
                if theme_slug:
                    await self._registry.upsert_theme(
                        tenant_id, theme_slug, theme
                    )
                    updated = True
        except Exception as exc:
            logger.warning("Theme registry update failed: %s", exc)

        # Add daily sentiment entry
        try:
            if sentiment:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                await self._registry.add_daily_sentiment(
                    tenant_id, date_str, sentiment
                )
                updated = True
        except Exception as exc:
            logger.warning("Sentiment daily update failed: %s", exc)

        # Add monthly NPS entry
        try:
            if nps_data and nps_data.get("score") is not None:
                period = nps_data.get(
                    "period",
                    datetime.now(timezone.utc).strftime("%Y-%m"),
                )
                await self._registry.add_monthly_nps(
                    tenant_id, period, nps_data
                )
                updated = True
        except Exception as exc:
            logger.warning("NPS monthly update failed: %s", exc)

        # Add data coverage score
        try:
            if coverage_data and coverage_data.get("score") is not None:
                await self._registry.add_coverage_score(
                    tenant_id,
                    score=coverage_data["score"],
                    channels=coverage_data.get("channels", []),
                    mode=coverage_data.get("mode", "external_only"),
                )
                updated = True
        except Exception as exc:
            logger.warning("Coverage score update failed: %s", exc)

        # Update last synthesis timestamp
        try:
            if updated:
                await self._registry.set_last_synthesis(
                    tenant_id,
                    datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            logger.warning("Last synthesis timestamp update failed: %s", exc)

        return updated

    # ── Insight Alert Emission ──

    async def _emit_insight_alerts(
        self,
        tenant_id: str,
        sentiment: dict[str, Any],
        nps_data: dict[str, Any],
        themes: list[dict[str, Any]],
    ) -> int:
        """Evaluate alert triggers and emit VoC insight alerts to Kafka."""
        if not self._alert_producer:
            return 0

        alerts_emitted = 0

        # Trigger 1: Critical negative sentiment (>60% negative)
        try:
            negative_pct = sentiment.get("negative", 0)
            total = (
                sentiment.get("positive", 0)
                + sentiment.get("negative", 0)
                + sentiment.get("neutral", 0)
            )
            if total > 0:
                negative_ratio = negative_pct / total
                if negative_ratio > 0.60:
                    await self._alert_producer.send_alert(
                        tenant_id=tenant_id,
                        alert_id=str(uuid.uuid4()),
                        alert_type="critical_negative_sentiment",
                        severity="critical",
                        title="Critical Negative Sentiment Detected",
                        description=(
                            f"Negative sentiment ratio at "
                            f"{negative_ratio:.1%}, exceeding 60% threshold."
                        ),
                        recommendation=(
                            "Investigate root causes of customer dissatisfaction "
                            "and prioritize remediation of top complaint themes."
                        ),
                        data={
                            "negative_ratio": round(negative_ratio, 4),
                            "sentiment_breakdown": sentiment,
                        },
                    )
                    alerts_emitted += 1
        except Exception as exc:
            logger.warning("Sentiment alert emission failed: %s", exc)

        # Trigger 2: NPS drop >10 points
        try:
            current_nps = nps_data.get("score")
            previous_nps = nps_data.get("previous_score")
            if current_nps is not None and previous_nps is not None:
                nps_drop = previous_nps - current_nps
                if nps_drop > 10:
                    await self._alert_producer.send_alert(
                        tenant_id=tenant_id,
                        alert_id=str(uuid.uuid4()),
                        alert_type="nps_drop",
                        severity="critical",
                        title="Significant NPS Drop Detected",
                        description=(
                            f"NPS dropped by {nps_drop} points "
                            f"(from {previous_nps} to {current_nps})."
                        ),
                        recommendation=(
                            "Conduct root cause analysis for NPS decline. "
                            "Review recent product changes, support interactions, "
                            "and competitive dynamics."
                        ),
                        data={
                            "current_nps": current_nps,
                            "previous_nps": previous_nps,
                            "nps_drop": nps_drop,
                        },
                    )
                    alerts_emitted += 1
        except Exception as exc:
            logger.warning("NPS alert emission failed: %s", exc)

        # Trigger 3: New critical theme
        try:
            for theme in themes:
                if theme.get("severity") == "critical" and theme.get("is_new", False):
                    await self._alert_producer.send_alert(
                        tenant_id=tenant_id,
                        alert_id=str(uuid.uuid4()),
                        alert_type="new_critical_theme",
                        severity="high",
                        title=f"New Critical Theme: {theme.get('name', 'Unknown')}",
                        description=(
                            f"A new critical feedback theme has been detected: "
                            f"{theme.get('name', 'Unknown')}. "
                            f"Mention count: {theme.get('mention_count', 0)}."
                        ),
                        recommendation=(
                            "Review this emerging theme and assess business impact. "
                            "Consider immediate response if customer-facing."
                        ),
                        data={
                            "theme_slug": theme.get("slug", ""),
                            "theme_name": theme.get("name", ""),
                            "mention_count": theme.get("mention_count", 0),
                            "sentiment": theme.get("sentiment", ""),
                        },
                    )
                    alerts_emitted += 1
        except Exception as exc:
            logger.warning("Theme alert emission failed: %s", exc)

        if alerts_emitted > 0:
            logger.info(
                "Emitted %d VoC insight alert(s) for tenant %s",
                alerts_emitted,
                tenant_id,
            )

        return alerts_emitted


def _elapsed(start: float) -> float:
    """Calculate elapsed time in milliseconds."""
    return (time.monotonic() - start) * 1000
