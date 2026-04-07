"""Metric extractor for the Intelligence Loop Agent (ILA, WF3.5).

Implements the contract from the ILA design document §12.1: pulls
extraction-run metadata from a completed AnalysisJob's ``result_data``
and emits MetricSnapshots tagged with the ``intelligence_loop`` category.

The extractor handles two shapes for ``result_data``:
- pipeline-driven runs (manifest ``meta-campaign-intelligence``):
    ``result_data['node_results']['campaign_intelligence']`` carries the
    payload returned by the ILA service ``/v1/execute`` endpoint.
- background runs (Kafka / Celery Beat triggered): the same payload is
    passed in directly at the top level of ``result_data``.
"""

from analytics.extractors.base import BaseExtractor


class IntelligenceLoopExtractor(BaseExtractor):
    """Extracts metrics from ILA extraction runs."""

    AGENT_SOURCE = "intelligence-loop-agent"
    CATEGORY = "intelligence_loop"

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {}) or {}

        # Try the pipeline-node payload first; fall back to top-level.
        ila = node_results.get("campaign_intelligence")
        if not ila:
            ila = result if result.get("intelligence_report") else {}
        if not isinstance(ila, dict):
            return []

        learnings = ila.get("scored_learnings") or ila.get("learnings") or []
        if not isinstance(learnings, list):
            learnings = []

        metadata = {
            "brand_context_id": ila.get("brand_context_id")
            or result.get("brand_context_id", "parent"),
            "intelligence_mode": ila.get("mode")
            or result.get("mode", "store_only"),
        }

        def _make(name, value):
            return self._make_metric(
                job,
                name,
                float(value),
                self.CATEGORY,
                unit="count",
                agent_source=self.AGENT_SOURCE,
                metadata=metadata,
            )

        high_conf = sum(
            1
            for l in learnings
            if isinstance(l, dict)
            and (l.get("final_confidence") or l.get("confidence") or 0) >= 85
        )
        high_impact = sum(
            1
            for l in learnings
            if isinstance(l, dict) and l.get("impact") == "HIGH"
        )

        contradictions = ila.get("contradictions") or []
        if not isinstance(contradictions, list):
            contradictions = []

        metrics = [
            _make("learnings_extracted", len(learnings)),
            _make("high_confidence_learnings", high_conf),
            _make("high_impact_learnings", high_impact),
            _make("auto_reruns_triggered", ila.get("auto_reruns_triggered", 0) or 0),
            _make("contradictions_detected", len(contradictions)),
            _make("rag_documents_written", ila.get("rag_writes", 0) or 0),
        ]
        return [m for m in metrics if m.metric_value is not None]
