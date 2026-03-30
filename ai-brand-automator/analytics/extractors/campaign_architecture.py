from analytics.extractors.base import BaseExtractor


class CampaignArchitectureExtractor(BaseExtractor):
    """Extracts metrics from campaign architecture (CAA) results.

    Data lives under result_data["node_results"]["campaign_architecture"].
    Extracts ~10 metrics covering funnel structure, budget allocation,
    audience targeting, testing, and overall confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        caa = node_results.get("campaign_architecture", {})
        if not caa:
            caa = result  # fallback for direct result_data
        metrics = []

        # Funnel stages count
        funnel_map = caa.get("funnel_map", {})
        stages = funnel_map.get("stages", [])
        if isinstance(stages, list) and stages:
            metrics.append(
                self._make_metric(
                    job,
                    "campaign_funnel_stages_count",
                    float(len(stages)),
                    "campaign_architecture",
                    unit="count",
                    agent_source="campaign-architecture-agent",
                )
            )

            # Budget allocation per funnel stage
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                stage_name = stage.get("stage", "").lower()
                budget_pct = stage.get("budget_pct")
                if budget_pct is not None and stage_name in (
                    "tofu",
                    "mofu",
                    "bofu",
                    "retention",
                ):
                    metrics.append(
                        self._make_metric(
                            job,
                            f"budget_{stage_name}_pct",
                            (
                                float(budget_pct) * 100
                                if float(budget_pct) <= 1
                                else float(budget_pct)
                            ),
                            "campaign_architecture",
                            unit="percent",
                            agent_source="campaign-architecture-agent",
                        )
                    )

        # Audience segments count (from blueprint ad_sets)
        blueprint = caa.get("blueprint", {})
        ad_sets = []
        if isinstance(blueprint, dict):
            ad_sets = blueprint.get("ad_sets", [])
            if isinstance(ad_sets, list) and ad_sets:
                metrics.append(
                    self._make_metric(
                        job,
                        "audience_segments_count",
                        float(len(ad_sets)),
                        "campaign_architecture",
                        unit="count",
                        agent_source="campaign-architecture-agent",
                    )
                )

            # Daily budget total
            campaign = blueprint.get("campaign", {})
            if isinstance(campaign, dict):
                daily_budget = campaign.get("daily_budget")
                if daily_budget is not None:
                    metrics.append(
                        self._make_metric(
                            job,
                            "daily_budget_total",
                            float(daily_budget),
                            "campaign_architecture",
                            unit="currency",
                            agent_source="campaign-architecture-agent",
                        )
                    )

        # A/B test variants planned
        test_plan = caa.get("test_plan", {})
        if isinstance(test_plan, dict):
            total_variants = test_plan.get("total_variants")
            if total_variants is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "ab_test_variants_planned",
                        float(total_variants),
                        "campaign_architecture",
                        unit="count",
                        agent_source="campaign-architecture-agent",
                    )
                )

        # Estimated reach
        projections = caa.get("performance_projections", {})
        if isinstance(projections, dict):
            reach = projections.get("estimated_reach")
            if reach is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "estimated_reach",
                        float(reach),
                        "campaign_architecture",
                        unit="count",
                        agent_source="campaign-architecture-agent",
                    )
                )

        # Overall confidence
        confidence = caa.get("confidence_score")
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "campaign_architecture_confidence",
                    (
                        float(confidence) * 100
                        if float(confidence) <= 1
                        else float(confidence)
                    ),
                    "campaign_architecture",
                    agent_source="campaign-architecture-agent",
                )
            )

        # Execution time
        exec_time = caa.get("execution_time_ms")
        if exec_time is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "campaign_architecture_execution_time",
                    float(exec_time),
                    "campaign_architecture",
                    unit="milliseconds",
                    agent_source="campaign-architecture-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
