from analytics.extractors.base import BaseExtractor


class BrandDiscoveryExtractor(BaseExtractor):
    """Extracts metrics from brand-discovery pipelines.

    Covers VoC, TCIA, APA, and CIA agent outputs.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        metrics = []

        # VoC metrics
        voc = result.get("voc_analysis", {})
        if voc:
            metrics.extend(self._extract_voc(job, voc))

        # TCIA metrics
        tcia = result.get("trend_cultural_analysis", {})
        if tcia:
            metrics.extend(self._extract_tcia(job, tcia))

        # APA metrics
        apa = result.get("audience_persona_analysis", {})
        if apa:
            metrics.extend(self._extract_apa(job, apa))

        # CIA metrics
        cia = result.get("competitor_intelligence", {})
        if cia:
            metrics.extend(self._extract_cia(job, cia))

        return metrics

    def _extract_voc(self, job, voc: dict) -> list:
        metrics = []

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

        # Sentiment percentages
        sentiment = voc.get("sentiment_distribution", {})
        if sentiment:
            pos = self._safe_get(sentiment, "positive", default=0)
            neg = self._safe_get(sentiment, "negative", default=0)
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

        # NPS — actual structure: nps.current_nps.nps_score
        nps_data = voc.get("nps", {})
        nps_score = self._safe_get(nps_data, "current_nps", "nps_score", default=None)
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

        # Pain points count
        pain_points = voc.get("pain_points", [])
        if isinstance(pain_points, list):
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

        # Data coverage
        coverage = self._safe_get(voc, "data_coverage_pct", default=None)
        if coverage is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "data_coverage_pct",
                    float(coverage),
                    "customer_voice",
                    unit="percent",
                    agent_source="voc-agent",
                )
            )

        return metrics

    def _extract_tcia(self, job, tcia: dict) -> list:
        metrics = []
        trends = tcia.get("trends", [])
        if isinstance(trends, list):
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
        if isinstance(personas, list):
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
        # Actual CIA result has competitors_analyzed as a list
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
        return metrics
