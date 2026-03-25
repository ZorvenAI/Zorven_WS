from analytics.extractors.base import BaseExtractor


class BrandPersonalityExtractor(BaseExtractor):
    """Extracts metrics from brand personality (BPV) results.

    Data lives under result_data["node_results"]["brand_personality"].
    Extracts 12 metrics covering Aaker dimensions, archetype resonance,
    values, emotional consistency, and overall confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        bpv = node_results.get("brand_personality", {})
        if not bpv:
            bpv = result  # fallback for direct result_data
        metrics = []

        # Aaker 5-dimension scores
        aaker = bpv.get("aaker_profile", {})
        if isinstance(aaker, dict):
            for dim in aaker.get("dimensions", []):
                if not isinstance(dim, dict):
                    continue
                dim_name = (dim.get("dimension", "") or "").lower()
                score = dim.get("score")
                if dim_name and score is not None:
                    metric_name = f"aaker_{dim_name}_score"
                    metrics.append(
                        self._make_metric(
                            job,
                            metric_name,
                            float(score),
                            "brand_personality",
                            agent_source="brand-personality-agent",
                        )
                    )

            # Differentiation score
            diff = self._safe_get(aaker, "differentiation_score", default=None)
            if diff is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "personality_differentiation",
                        float(diff),
                        "brand_personality",
                        agent_source="brand-personality-agent",
                    )
                )

        # Archetype resonance score
        archetype = bpv.get("archetype", {})
        if isinstance(archetype, dict):
            resonance = self._safe_get(
                archetype, "resonance_score", default=None
            )
            if resonance is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "archetype_resonance_score",
                        float(resonance),
                        "brand_personality",
                        agent_source="brand-personality-agent",
                    )
                )

        # Values authenticity score
        values = bpv.get("values_hierarchy", {})
        if isinstance(values, dict):
            auth = self._safe_get(values, "authenticity_score", default=None)
            if auth is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "values_authenticity_score",
                        float(auth),
                        "brand_personality",
                        agent_source="brand-personality-agent",
                    )
                )
            # Core values count
            core = values.get("core", [])
            if isinstance(core, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "core_values_count",
                        float(len(core)),
                        "brand_personality",
                        unit="count",
                        agent_source="brand-personality-agent",
                    )
                )

        # Emotional consistency score
        emo_map = bpv.get("emotional_map", {})
        if isinstance(emo_map, dict):
            consistency = self._safe_get(
                emo_map, "consistency_score", default=None
            )
            if consistency is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "emotional_consistency_score",
                        float(consistency),
                        "brand_personality",
                        agent_source="brand-personality-agent",
                    )
                )

        # Character brief positioning alignment
        brief = bpv.get("character_brief", {})
        if isinstance(brief, dict):
            alignment = self._safe_get(
                brief, "positioning_alignment_score", default=None
            )
            if alignment is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "personality_positioning_alignment",
                        float(alignment),
                        "brand_personality",
                        agent_source="brand-personality-agent",
                    )
                )

        # Overall personality confidence
        confidence = bpv.get("confidence_score")
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "personality_confidence",
                    float(confidence) * 100,  # normalize 0-1 to 0-100
                    "brand_personality",
                    agent_source="brand-personality-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
