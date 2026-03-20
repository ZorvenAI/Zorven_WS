from analytics.extractors.base import BaseExtractor


class BrandEquityExtractor(BaseExtractor):
    """Extracts metrics from iso-brand-equity pipeline.

    Data may be at top level or under node_results.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # Try multiple paths for brand equity data
        equity = result.get("brand_equity", {})
        if not equity:
            equity = result.get("valuation", {}).get("brand_equity", {})
        if not equity:
            # Check under node_results (intelligence node)
            intel = node_results.get("intelligence", {})
            if not intel:
                intel = node_results.get("brand_equity_calculator", {})
            if intel:
                equity = intel.get("brand_equity", {})
                if not equity:
                    equity = intel.get("valuation", {}).get("brand_equity", {})

        awareness = self._safe_get(equity, "awareness", default=None)
        if awareness is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "brand_equity_awareness",
                    float(awareness),
                    "brand_equity",
                    agent_source="intelligence-agent",
                )
            )

        sentiment = self._safe_get(equity, "sentiment", default=None)
        if sentiment is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "brand_equity_sentiment",
                    float(sentiment),
                    "brand_equity",
                    agent_source="intelligence-agent",
                )
            )

        financials = self._safe_get(equity, "financials", default=None)
        if financials is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "brand_equity_financials",
                    float(financials),
                    "brand_equity",
                    agent_source="intelligence-agent",
                )
            )

        # Brand value NPV — check multiple paths
        npv = self._safe_get(result, "brand_value", "npv", default=None)
        if npv is None:
            npv = self._safe_get(result, "valuation", "brand_value_npv", default=None)
        if npv is None and node_results:
            intel = node_results.get(
                "intelligence", node_results.get("brand_equity_calculator", {})
            )
            if isinstance(intel, dict):
                npv = self._safe_get(intel, "brand_value", "npv", default=None)
                if npv is None:
                    npv = self._safe_get(
                        intel, "valuation", "brand_value_npv", default=None
                    )
        if npv is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "brand_value_npv",
                    float(npv),
                    "brand_equity",
                    unit="currency",
                    agent_source="intelligence-agent",
                )
            )

        return metrics
