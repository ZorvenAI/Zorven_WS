from analytics.extractors.base import BaseExtractor


class BrandEquityExtractor(BaseExtractor):
    """Extracts metrics from iso-brand-equity pipeline."""

    def extract(self, job) -> list:
        result = job.result_data or {}
        metrics = []

        # Brand equity scores (ISO 10668 dimensions)
        equity = result.get("brand_equity", {})
        if not equity:
            # Try alternate key structure
            equity = result.get("valuation", {}).get("brand_equity", {})

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

        # Brand value NPV
        npv = self._safe_get(result, "brand_value", "npv", default=None)
        if npv is None:
            npv = self._safe_get(result, "valuation", "brand_value_npv", default=None)
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
