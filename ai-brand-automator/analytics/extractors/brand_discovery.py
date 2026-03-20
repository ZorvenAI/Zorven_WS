from analytics.extractors.base import BaseExtractor


class BrandDiscoveryExtractor(BaseExtractor):
    """Extracts metrics from brand-discovery pipelines.

    Covers VoC, TCIA, APA, and CIA agent outputs.
    Data lives under result_data["node_results"][<node_id>].
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # VoC metrics — node_id: "voice_of_customer"
        voc = node_results.get("voice_of_customer", {})
        if not voc:
            voc = result.get("voice_of_customer", {})
        if voc:
            metrics.extend(self._extract_voc(job, voc))

        # TCIA metrics — node_id: "trend_cultural"
        tcia = node_results.get("trend_cultural", {})
        if not tcia:
            tcia = result.get("trend_cultural", {})
        if tcia:
            metrics.extend(self._extract_tcia(job, tcia))

        # APA metrics — node_id: "audience_persona"
        apa = node_results.get("audience_persona", {})
        if not apa:
            apa = result.get("audience_persona", {})
        if apa:
            metrics.extend(self._extract_apa(job, apa))

        # CIA metrics — node_id: "competitor_intelligence"
        cia = node_results.get("competitor_intelligence", {})
        if not cia:
            cia = result.get("competitor_intelligence", {})
        if cia:
            metrics.extend(self._extract_cia(job, cia))

        return metrics

    def _extract_voc(self, job, voc: dict) -> list:
        metrics = []

        # VoC health score — top-level key in service response
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

        # Sentiment percentages — voc.sentiment.overall_sentiment
        sentiment = voc.get("sentiment", {})
        overall = sentiment.get("overall_sentiment", {}) if sentiment else {}
        if overall:
            pos = self._safe_get(overall, "positive", default=0)
            neg = self._safe_get(overall, "negative", default=0)
            # Convert from 0-1 ratio to percentage if needed
            if isinstance(pos, (int, float)) and pos <= 1.0:
                pos = pos * 100
            if isinstance(neg, (int, float)) and neg <= 1.0:
                neg = neg * 100
            metrics.append(
                self._make_metric(
                    job,
                    "sentiment_positive_pct",
                    float(pos),
                    "customer_voice",
                    unit="percent",
                    agent_source="voc-agent",
                )
            )
            metrics.append(
                self._make_metric(
                    job,
                    "sentiment_negative_pct",
                    float(neg),
                    "customer_voice",
                    unit="percent",
                    agent_source="voc-agent",
                )
            )

        # NPS — voc.nps_analysis.current_nps.nps_score
        nps_data = voc.get("nps_analysis", {})
        if isinstance(nps_data, dict):
            nps_score = self._safe_get(
                nps_data, "current_nps", "nps_score", default=None
            )
            # Also check proxy NPS
            if nps_score is None:
                nps_score = self._safe_get(
                    nps_data, "proxy_nps", "nps_score", default=None
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

        # Pain points count — voc.pain_point_priority_matrix.pain_points
        pain_matrix = voc.get("pain_point_priority_matrix", {})
        pain_points = (
            pain_matrix.get("pain_points", []) if isinstance(pain_matrix, dict) else []
        )
        if isinstance(pain_points, list) and pain_points:
            metrics.append(
                self._make_metric(
                    job,
                    "pain_points_count",
                    float(len(pain_points)),
                    "customer_voice",
                    unit="count",
                    agent_source="voc-agent",
                )
            )

        # Data coverage — voc.data_coverage_score
        coverage = self._safe_get(voc, "data_coverage_score", default=None)
        if coverage is not None:
            # Convert 0-1 to percentage
            cov_val = float(coverage)
            if cov_val <= 1.0:
                cov_val = cov_val * 100
            metrics.append(
                self._make_metric(
                    job,
                    "data_coverage_pct",
                    cov_val,
                    "customer_voice",
                    unit="percent",
                    agent_source="voc-agent",
                )
            )

        return metrics

    def _extract_tcia(self, job, tcia: dict) -> list:
        metrics = []
        # scored_trends is a list of trend objects
        trends = tcia.get("scored_trends", [])
        if not trends:
            # Fallback: check trend_report for trends
            report = tcia.get("trend_report", {})
            if isinstance(report, dict):
                trends = report.get("trend_scorecard", [])
        if isinstance(trends, list) and trends:
            metrics.append(
                self._make_metric(
                    job,
                    "trends_identified",
                    float(len(trends)),
                    "trend_analysis",
                    unit="count",
                    agent_source="trend-cultural-agent",
                )
            )
        return metrics

    def _extract_apa(self, job, apa: dict) -> list:
        metrics = []
        personas = apa.get("personas", [])
        if isinstance(personas, list) and personas:
            metrics.append(
                self._make_metric(
                    job,
                    "personas_count",
                    float(len(personas)),
                    "audience",
                    unit="count",
                    agent_source="audience-persona-agent",
                )
            )
        return metrics

    def _extract_cia(self, job, cia: dict) -> list:
        metrics = []
        competitors = cia.get("competitors_analyzed", [])
        if not competitors:
            # Fallback: competitors list with dicts
            raw = cia.get("competitors", [])
            if isinstance(raw, list):
                competitors = [c.get("name", "") for c in raw if isinstance(c, dict)]
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
        return metrics
