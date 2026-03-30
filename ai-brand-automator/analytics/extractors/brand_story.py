from analytics.extractors.base import BaseExtractor


class BrandStoryExtractor(BaseExtractor):
    """Extracts metrics from brand story & narrative (BSA) results.

    Data lives under result_data["node_results"]["brand_story"].
    Extracts 11 metrics covering narrative quality, alignment,
    and overall confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        bsa = node_results.get("brand_story", {})
        if not bsa:
            bsa = result  # fallback for direct result_data
        metrics = []

        # Origin story scores (from best version)
        origin = bsa.get("origin_story", {})
        versions = origin.get("versions", [])
        if isinstance(versions, list) and versions:
            # Use medium version (index 1) or first available
            best = versions[1] if len(versions) > 1 else versions[0]
            if isinstance(best, dict):
                for metric_key, field in (
                    ("story_archetype_arc_alignment", "archetype_arc_alignment"),
                    ("story_emotional_resonance", "emotional_resonance_score"),
                    ("story_voice_consistency", "voice_consistency_score"),
                ):
                    val = best.get(field)
                    if val is not None:
                        metrics.append(
                            self._make_metric(
                                job,
                                metric_key,
                                float(val) * 100,  # normalize 0-1 to 0-100
                                "brand_story",
                                agent_source="brand-story-agent",
                            )
                        )

        # Mission/Vision scores (handle both nested and flat paths)
        mv = bsa.get("mission_vision", {})
        mission_obj = mv.get("mission", {})
        mission_scores = (
            mission_obj.get("scores", {}) if isinstance(mission_obj, dict) else {}
        ) or mv.get("mission_scores", {})
        if isinstance(mission_scores, dict):
            clarity = mission_scores.get("clarity")
            if clarity is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "mission_clarity",
                        float(clarity) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )
            pos_align = mission_scores.get("positioning_alignment")
            if pos_align is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "mission_positioning_alignment",
                        float(pos_align) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )

        vision_obj = mv.get("vision", {})
        vision_scores = (
            vision_obj.get("scores", {}) if isinstance(vision_obj, dict) else {}
        ) or mv.get("vision_scores", {})
        if isinstance(vision_scores, dict):
            inspiration = vision_scores.get("inspiration")
            if inspiration is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "vision_inspiration",
                        float(inspiration) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )

        # Pitch memorability (30s pitch)
        pitches = bsa.get("pitches", {})
        pitch_30s = pitches.get("pitch_30s", {})
        if isinstance(pitch_30s, dict):
            mem = pitch_30s.get("memorability_score")
            if mem is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "pitch_30s_memorability",
                        float(mem) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )

        # Channel narrative consistency
        channels = bsa.get("channel_narratives", {})
        if isinstance(channels, dict):
            consistency = channels.get("channel_consistency_score")
            if consistency is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "channel_narrative_consistency",
                        float(consistency) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )

        # Narrative package scores
        pkg = bsa.get("narrative_package", {})
        if isinstance(pkg, dict):
            overall_conf = pkg.get("overall_confidence")
            if overall_conf is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "narrative_overall_confidence",
                        float(overall_conf) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )
            pos_narrative = pkg.get("positioning_narrative_alignment")
            if pos_narrative is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "narrative_positioning_alignment",
                        float(pos_narrative) * 100,
                        "brand_story",
                        agent_source="brand-story-agent",
                    )
                )

        # Overall confidence
        confidence = bsa.get("confidence_score")
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "story_confidence",
                    float(confidence) * 100,
                    "brand_story",
                    agent_source="brand-story-agent",
                )
            )

        # Execution time
        exec_time = bsa.get("execution_time_ms")
        if exec_time is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "story_execution_time",
                    float(exec_time),
                    "brand_story",
                    unit="milliseconds",
                    agent_source="brand-story-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
