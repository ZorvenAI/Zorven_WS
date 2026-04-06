from analytics.extractors.base import BaseExtractor


class ContinuousOptimizationExtractor(BaseExtractor):
    """Extracts metrics from COA optimization tick results.

    Unlike other extractors, this is NOT called via PIPELINE_EXTRACTORS
    (COA is not pipeline-triggered). Instead, the optimization tick callback
    view triggers metric extraction directly.

    Expects tick_results dict with keys:
        - recommendations: list of recommendation dicts
        - auto_actions: int count of auto-executed actions
        - performance: {avg_cpa, avg_roas, avg_ctr, spend_today}
        - fatigued_ads: list of fatigued ad dicts
        - mode: "manual" | "autonomous"
        - brand_context_id: str
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # COA stores tick results under "continuous_optimization" key
        tick = node_results.get("continuous_optimization", {})
        if not tick:
            tick = result.get("continuous_optimization", {})
        if not tick:
            tick = result

        if not tick or not isinstance(tick, dict):
            return metrics

        mode = tick.get("mode", "manual")
        brand_ctx = tick.get("brand_context_id", "parent")
        metadata = {
            "optimization_mode": mode,
            "brand_context_id": brand_ctx,
        }

        # Recommendations generated
        recs = tick.get("recommendations", [])
        if isinstance(recs, list):
            metrics.append(
                self._make_metric(
                    job,
                    "recommendations_generated",
                    float(len(recs)),
                    "optimization",
                    unit="count",
                    agent_source="campaign-optimization-agent",
                    metadata=metadata,
                )
            )

            approved_count = sum(
                1 for r in recs if isinstance(r, dict) and r.get("status") == "approved"
            )
            metrics.append(
                self._make_metric(
                    job,
                    "recommendations_approved",
                    float(approved_count),
                    "optimization",
                    unit="count",
                    agent_source="campaign-optimization-agent",
                    metadata=metadata,
                )
            )

        # Auto-actions executed
        auto_actions = tick.get("auto_actions", 0)
        if isinstance(auto_actions, (int, float)):
            metrics.append(
                self._make_metric(
                    job,
                    "auto_actions_executed",
                    float(auto_actions),
                    "optimization",
                    unit="count",
                    agent_source="campaign-optimization-agent",
                    metadata=metadata,
                )
            )

        # Performance metrics passthrough
        perf = tick.get("performance", {})
        if perf and isinstance(perf, dict):
            avg_cpa = perf.get("avg_cpa")
            if avg_cpa and isinstance(avg_cpa, (int, float)) and avg_cpa > 0:
                metrics.append(
                    self._make_metric(
                        job,
                        "campaign_cpa",
                        float(avg_cpa),
                        "optimization",
                        unit="currency",
                        agent_source="campaign-optimization-agent",
                        metadata=metadata,
                    )
                )

            avg_roas = perf.get("avg_roas")
            if avg_roas and isinstance(avg_roas, (int, float)) and avg_roas > 0:
                metrics.append(
                    self._make_metric(
                        job,
                        "campaign_roas",
                        float(avg_roas),
                        "optimization",
                        unit="ratio",
                        agent_source="campaign-optimization-agent",
                        metadata=metadata,
                    )
                )

            avg_ctr = perf.get("avg_ctr")
            if avg_ctr and isinstance(avg_ctr, (int, float)):
                metrics.append(
                    self._make_metric(
                        job,
                        "campaign_ctr",
                        float(avg_ctr),
                        "optimization",
                        unit="percent",
                        agent_source="campaign-optimization-agent",
                        metadata=metadata,
                    )
                )

            spend_today = perf.get("spend_today")
            if spend_today and isinstance(spend_today, (int, float)) and spend_today > 0:
                metrics.append(
                    self._make_metric(
                        job,
                        "campaign_spend_today",
                        float(spend_today),
                        "optimization",
                        unit="currency",
                        agent_source="campaign-optimization-agent",
                        metadata=metadata,
                    )
                )

        # Fatigued ads count
        fatigued = tick.get("fatigued_ads", [])
        if isinstance(fatigued, list):
            metrics.append(
                self._make_metric(
                    job,
                    "fatigued_ads_count",
                    float(len(fatigued)),
                    "optimization",
                    unit="count",
                    agent_source="campaign-optimization-agent",
                    metadata=metadata,
                )
            )

        return metrics
