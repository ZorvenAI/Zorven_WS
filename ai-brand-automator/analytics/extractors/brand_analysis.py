from analytics.extractors.base import BaseExtractor


class BrandAnalysisExtractor(BaseExtractor):
    """Extracts metrics from brand-analysis and competitor-audit pipelines.

    Reuses CIA + VoC extraction logic from the brand discovery extractor.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        metrics = []

        # CIA metrics
        cia = result.get("competitor_intelligence", {})
        if cia:
            competitors = cia.get("competitors_analyzed", [])
            if isinstance(competitors, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "competitors_tracked",
                        float(len(competitors)),
                        "competitive",
                        unit="count",
                        agent_source="competitor-intel-agent",
                    )
                )

        # VoC metrics (if present in brand-analysis results)
        voc = result.get("voc_analysis", {})
        if voc:
            health_score = self._safe_get(voc, "health_score")
            if health_score:
                metrics.append(
                    self._make_metric(
                        job,
                        "voc_health_score",
                        float(health_score),
                        "customer_voice",
                        agent_source="voc-agent",
                    )
                )

            nps_data = voc.get("nps", {})
            nps_score = self._safe_get(
                nps_data, "current_nps", "nps_score", default=None
            )
            if nps_score is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "nps",
                        float(nps_score),
                        "customer_voice",
                        unit="score",
                        agent_source="voc-agent",
                    )
                )

        return metrics
