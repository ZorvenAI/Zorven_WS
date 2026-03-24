from analytics.extractors.base import BaseExtractor


class BrandArchitectureExtractor(BaseExtractor):
    """Extracts metrics from brand architecture (BAA) results.

    Data lives under result_data["node_results"]["brand_architecture"].
    Extracts 10 metrics covering architecture model scoring, hierarchy,
    naming consistency, growth planning, and confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        baa = node_results.get("brand_architecture", {})
        if not baa:
            baa = result  # fallback for direct result_data
        metrics = []

        # Architecture model scores (from recommended model)
        rec = baa.get("recommendation", {})
        if isinstance(rec, dict):
            recommended_model = rec.get("recommended_model", "")
            model_scores = rec.get("model_scores", [])

            # Find the recommended model's scores
            rec_scores = None
            for ms in model_scores:
                if isinstance(ms, dict) and ms.get("model") == recommended_model:
                    rec_scores = ms
                    break
            if not rec_scores and model_scores:
                rec_scores = (
                    model_scores[0] if isinstance(model_scores[0], dict) else {}
                )

            if rec_scores:
                total = self._safe_get(rec_scores, "total", default=None)
                if total is not None:
                    metrics.append(
                        self._make_metric(
                            job,
                            "architecture_model_score",
                            float(total),
                            "brand_architecture",
                            agent_source="brand-architecture-agent",
                        )
                    )

                for dim in (
                    "positioning_alignment",
                    "audience_fit",
                    "competitive_diff",
                    "operational_efficiency",
                ):
                    v = self._safe_get(rec_scores, dim, default=None)
                    if v is not None:
                        metrics.append(
                            self._make_metric(
                                job,
                                f"architecture_{dim}",
                                float(v),
                                "brand_architecture",
                                agent_source="brand-architecture-agent",
                            )
                        )

        # Hierarchy metrics
        hierarchy = baa.get("hierarchy", {})
        if isinstance(hierarchy, dict):
            depth = self._safe_get(hierarchy, "total_depth", default=None)
            if depth is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "hierarchy_depth",
                        float(depth),
                        "brand_architecture",
                        unit="count",
                        agent_source="brand-architecture-agent",
                    )
                )

            total_nodes = self._safe_get(hierarchy, "total_nodes", default=None)
            if total_nodes is not None:
                sub_brand_count = max(float(total_nodes) - 1, 0)
                metrics.append(
                    self._make_metric(
                        job,
                        "sub_brand_count",
                        sub_brand_count,
                        "brand_architecture",
                        unit="count",
                        agent_source="brand-architecture-agent",
                    )
                )

        # Naming consistency
        naming = baa.get("naming_hierarchy", {})
        if isinstance(naming, dict):
            cs = self._safe_get(naming, "consistency_score", default=None)
            if cs is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "naming_consistency_score",
                        float(cs),
                        "brand_architecture",
                        agent_source="brand-architecture-agent",
                    )
                )

        # Growth phases planned
        growth = baa.get("growth_path", {})
        if isinstance(growth, dict):
            phases = growth.get("phases", [])
            if isinstance(phases, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "growth_phases_planned",
                        float(len(phases)),
                        "brand_architecture",
                        unit="count",
                        agent_source="brand-architecture-agent",
                    )
                )

        # Architecture confidence
        confidence = baa.get("confidence_score")
        if confidence is None:
            confidence = rec.get("confidence_score") if isinstance(rec, dict) else None
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "architecture_confidence",
                    float(confidence) * 100,  # normalize 0-1 to 0-100
                    "brand_architecture",
                    agent_source="brand-architecture-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
