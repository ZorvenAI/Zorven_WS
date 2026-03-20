from analytics.extractors.base import BaseExtractor


class BrandAnalysisExtractor(BaseExtractor):
    """Extracts metrics from brand-analysis and competitor-audit pipelines.

    Reuses CIA + VoC extraction logic.
    Data lives under result_data["node_results"][<node_id>].
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # CIA metrics — node_id: "competitor_intelligence"
        cia = node_results.get("competitor_intelligence", {})
        if not cia:
            cia = result.get("competitor_intelligence", {})
        if cia:
            competitors = cia.get("competitors_analyzed", [])
            if not competitors:
                raw = cia.get("competitors", [])
                if isinstance(raw, list):
                    competitors = [
                        c.get("name", "") for c in raw if isinstance(c, dict)
                    ]
                    competitors = [n for n in competitors if n]
            if isinstance(competitors, list) and competitors:
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

        # VoC metrics — node_id: "voice_of_customer"
        voc = node_results.get("voice_of_customer", {})
        if not voc:
            voc = result.get("voice_of_customer", {})
        if voc:
            health_score = self._safe_get(voc, "voc_health_score")
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

            nps_data = voc.get("nps_analysis", {})
            if isinstance(nps_data, dict):
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
