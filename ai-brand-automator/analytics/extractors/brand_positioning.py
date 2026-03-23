from analytics.extractors.base import BaseExtractor


class BrandPositioningExtractor(BaseExtractor):
    """Extracts metrics from brand positioning (BPA) results.

    Data lives under result_data["node_results"]["brand_positioning"].
    Extracts 13 metrics covering positioning quality, differentiation,
    value proposition canvas, perceptual maps, and candidate generation.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        bpa = node_results.get("brand_positioning", {})
        if not bpa:
            bpa = result  # fallback for direct result_data
        metrics = []

        # Positioning quality scores (from recommended positioning)
        pos = bpa.get("recommended_positioning", {})
        if isinstance(pos, dict):
            scores = pos.get("scores", {})
            for dim in (
                "clarity",
                "differentiation",
                "believability",
                "memorability",
                "overall",
            ):
                v = self._safe_get(scores, dim, default=None)
                if v is not None:
                    metrics.append(
                        self._make_metric(
                            job,
                            f"positioning_{dim}_score",
                            float(v),
                            "brand_positioning",
                            agent_source="brand-positioning-agent",
                        )
                    )

        # Differentiation framework
        diff = bpa.get("differentiation", {})
        if isinstance(diff, dict):
            pods = diff.get("pods", [])
            pops = diff.get("pops", [])
            if isinstance(pods, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "points_of_difference_count",
                        float(len(pods)),
                        "brand_positioning",
                        unit="count",
                        agent_source="brand-positioning-agent",
                    )
                )
            if isinstance(pops, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "points_of_parity_count",
                        float(len(pops)),
                        "brand_positioning",
                        unit="count",
                        agent_source="brand-positioning-agent",
                    )
                )
            ds = self._safe_get(diff, "overall_differentiation_score", default=None)
            if ds is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "differentiation_score",
                        float(ds),
                        "brand_positioning",
                        agent_source="brand-positioning-agent",
                    )
                )

        # Value proposition canvas fit
        canvas = bpa.get("canvas", {})
        if isinstance(canvas, dict):
            fs = self._safe_get(canvas, "fit_score", default=None)
            if fs is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "value_prop_fit_score",
                        float(fs),
                        "brand_positioning",
                        agent_source="brand-positioning-agent",
                    )
                )

        # Perceptual maps
        maps = bpa.get("perceptual_maps", [])
        if isinstance(maps, list):
            metrics.append(
                self._make_metric(
                    job,
                    "perceptual_maps_generated",
                    float(len(maps)),
                    "brand_positioning",
                    unit="count",
                    agent_source="brand-positioning-agent",
                )
            )
            if maps:
                primary = next(
                    (
                        m
                        for m in maps
                        if isinstance(m, dict) and m.get("is_primary_recommended")
                    ),
                    maps[0] if maps else {},
                )
                if isinstance(primary, dict):
                    dp = self._safe_get(
                        primary, "differentiation_potential_score", default=None
                    )
                    if dp is not None:
                        metrics.append(
                            self._make_metric(
                                job,
                                "primary_map_differentiation_potential",
                                float(dp),
                                "brand_positioning",
                                agent_source="brand-positioning-agent",
                            )
                        )

            # White space zones
            ws_count = sum(
                len(m.get("white_space_highlighted", []))
                for m in maps
                if isinstance(m, dict)
            )
            metrics.append(
                self._make_metric(
                    job,
                    "competitive_white_space_zones",
                    float(ws_count),
                    "brand_positioning",
                    unit="count",
                    agent_source="brand-positioning-agent",
                )
            )

        # Candidate count
        candidates = bpa.get("positioning_candidates", [])
        if isinstance(candidates, list):
            metrics.append(
                self._make_metric(
                    job,
                    "positioning_candidates_generated",
                    float(len(candidates)),
                    "brand_positioning",
                    unit="count",
                    agent_source="brand-positioning-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
