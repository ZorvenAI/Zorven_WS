"""
ManagerNode — Aggregates node outputs into final result_data.

This is typically the terminal node in a pipeline. It collects
all previous node outputs and formats them for the frontend
ResultDashboard and BrandEquityDashboard components.
"""

from typing import Any

from app.nodes.base import BaseNode
from app.state.schema import AgentState

_RESEARCH_NODES = {"default_agent", "web_research"}
_MARKET_RESEARCH_NODES = {"market_research"}
_COMPETITOR_INTEL_NODES = {"competitor_intelligence"}
_AUDIENCE_PERSONA_NODES = {"audience_persona"}
_TREND_CULTURAL_NODES = {"trend_cultural"}
_VOICE_OF_CUSTOMER_NODES = {"voice_of_customer"}
_BRAND_POSITIONING_NODES = {"brand_positioning"}
_BRAND_ARCHITECTURE_NODES = {"brand_architecture"}
_BRAND_PERSONALITY_NODES = {"brand_personality"}
_BRAND_NAMING_NODES = {"brand_naming"}
_BRAND_STORY_NODES = {"brand_story"}
_CAMPAIGN_ARCHITECTURE_NODES = {"campaign_architecture"}


def _source_label(source: dict) -> str:
    """Extract a human-readable label from a source dict.

    Different upstream nodes use different field names for the source label:
    - DefaultAgentNode (RAG):   {"name": "...", "uri": "..."}
    - discovery-agent-svc:      {"title": "...", "url": "..."}
    """
    return source.get("name") or source.get("title") or ""


class ManagerNode(BaseNode):
    """Aggregates all node outputs into a structured result."""

    async def __call__(self, state: AgentState) -> dict:
        outputs = state.get("node_outputs", {})

        findings: list[str] = []
        recommendations: list[str] = []

        # When downstream processing nodes (blog_author, social_promoter, etc.)
        # have their own findings, replace the research node's verbose
        # conversational answer with a brief source summary.  This prevents
        # contradictory messages like "I cannot schedule posts" from the RAG
        # node appearing alongside "Scheduled on: linkedin, twitter" from the
        # social promoter.  In standalone chat (research + manager only) the
        # full answer is preserved.
        processing_nodes = {nid for nid in outputs if nid not in _RESEARCH_NODES}
        has_processing = bool(processing_nodes)

        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if has_processing and node_id in _RESEARCH_NODES:
                    # Summarise research sources instead of full findings
                    sources = output.get("sources", [])
                    source_names = [
                        _source_label(s) for s in sources if isinstance(s, dict)
                    ]
                    source_names = [n for n in source_names if n]
                    if source_names:
                        findings.append(
                            f"Research data retrieved from: "
                            f"{', '.join(source_names[:5])}"
                        )
                    continue
                findings.extend(output.get("findings", []))
                recommendations.extend(output.get("recommendations", []))

        # Extract BSI and valuation data from intelligence agent output
        bsi_data = self._extract_bsi(outputs)
        valuation_data = self._extract_valuation(outputs)

        # Extract market research data
        market_research_data = self._extract_market_research(outputs)

        # Extract competitor intelligence data
        competitor_intel_data = self._extract_competitor_intelligence(outputs)

        # Extract audience persona data
        audience_persona_data = self._extract_audience_persona(outputs)

        # Extract trend/cultural insights data
        trend_cultural_data = self._extract_trend_cultural(outputs)

        # Extract voice of customer data
        voice_of_customer_data = self._extract_voice_of_customer(outputs)

        # Extract brand positioning data
        brand_positioning_data = self._extract_brand_positioning(outputs)

        # Extract brand architecture data
        brand_architecture_data = self._extract_brand_architecture(outputs)

        # Extract brand personality data
        brand_personality_data = self._extract_brand_personality(outputs)

        # Extract brand naming data
        brand_naming_data = self._extract_brand_naming(outputs)

        # Extract brand story data
        brand_story_data = self._extract_brand_story(outputs)

        # Extract campaign architecture data
        campaign_arch_data = self._extract_campaign_architecture(outputs)

        result_data: dict[str, Any] = {
            "summary": (
                f"Pipeline analysis completed. "
                f"Processed {len(outputs)} agent(s) with results."
            ),
            "findings": findings or ["Analysis completed successfully."],
            "recommendations": recommendations
            or ["Review the detailed node outputs for actionable insights."],
            "node_results": outputs,
        }

        # Per-agent confidence scores (namespaced to avoid overwriting)
        confidence_scores: dict[str, float] = {}

        # Promote market research fields to top-level result_data
        if market_research_data:
            for key in (
                "market_overview",
                "market_sizing",
                "competitive_landscape",
                "industry_trends",
                "economic_indicators",
                "sources",
                "methodology_notes",
            ):
                value = market_research_data.get(key)
                if value is not None:
                    result_data[key] = value
            mra_conf = market_research_data.get("confidence_score")
            if mra_conf is not None:
                confidence_scores["market_research"] = mra_conf

        # Promote competitor intelligence fields to top-level result_data
        if competitor_intel_data:
            for key in (
                "competitors",
                "competitors_analyzed",
                "competitor_matrix",
                "swot_analyses",
                "positioning_gaps",
                "positioning_map",
                "benchmarking_report",
                "executive_summary",
                "methodology_notes",
            ):
                value = competitor_intel_data.get(key)
                if value is not None:
                    result_data[key] = value
            cia_conf = competitor_intel_data.get("confidence_score")
            if cia_conf is not None:
                confidence_scores["competitor_intelligence"] = cia_conf
            # Merge CIA sources with existing (from MRA)
            cia_sources = competitor_intel_data.get("sources", [])
            if cia_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in cia_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = cia_sources

        # Promote audience persona fields to top-level result_data
        if audience_persona_data:
            for key in (
                "personas",
                "journey_maps",
                "segment_matrix",
                "executive_summary",
                "methodology_notes",
            ):
                value = audience_persona_data.get(key)
                if value is not None:
                    result_data[key] = value
            apa_conf = audience_persona_data.get("confidence_score")
            if apa_conf is not None:
                confidence_scores["audience_persona"] = apa_conf
            # Merge APA sources with existing
            apa_sources = audience_persona_data.get("sources", [])
            if apa_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in apa_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = apa_sources

        # Promote trend/cultural insights fields to top-level result_data
        if trend_cultural_data:
            for key in (
                "trend_report",
                "scored_trends",
                "trend_persona_matrix",
                "opportunity_alerts",
                "viral_patterns",
                "cultural_shifts",
                "generational_insights",
                "language_trends",
                "report_url",
            ):
                value = trend_cultural_data.get(key)
                if value is not None:
                    result_data[key] = value
            tcia_conf = trend_cultural_data.get("confidence_score")
            if tcia_conf is not None:
                confidence_scores["trend_cultural"] = tcia_conf
            # Merge TCIA sources with existing
            tcia_sources = trend_cultural_data.get("sources", [])
            if tcia_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in tcia_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = tcia_sources

        # Promote voice of customer fields to top-level result_data
        if voice_of_customer_data:
            for key in (
                "voc_health_score",
                "operating_mode",
                "data_coverage_score",
                "sentiment",
                "themes",
                "nps_analysis",
                "pain_point_priority_matrix",
                "strategy_bridge",
                "odoo_onboarding_recommendation",
            ):
                value = voice_of_customer_data.get(key)
                if value is not None:
                    result_data[key] = value
            voca_conf = voice_of_customer_data.get("confidence_score")
            if voca_conf is not None:
                confidence_scores["voice_of_customer"] = voca_conf
            # Merge VoCA sources with existing
            voca_sources = voice_of_customer_data.get("sources", [])
            if voca_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in voca_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = voca_sources

        # Promote brand positioning fields to top-level result_data
        if brand_positioning_data:
            for key in (
                "recommended_positioning",
                "alternative_positions",
                "positioning_candidates",
                "canvas",
                "perceptual_maps",
                "differentiation",
                "strategy",
                "wf1_context_used",
            ):
                value = brand_positioning_data.get(key)
                if value is not None:
                    result_data[key] = value
            bpa_conf = brand_positioning_data.get("confidence_score")
            if bpa_conf is not None:
                confidence_scores["brand_positioning"] = bpa_conf
            # Build a richer summary from BPA data
            pos = brand_positioning_data.get("recommended_positioning", {})
            stmt = pos.get("statement", "")
            if stmt:
                result_data["summary"] = (
                    f"Brand positioning strategy generated. "
                    f"Recommended positioning: {stmt[:200]}"
                )
            # Merge BPA sources with existing
            bpa_sources = brand_positioning_data.get("sources", [])
            if bpa_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in bpa_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = bpa_sources

        # Promote brand architecture fields to top-level result_data
        if brand_architecture_data:
            for key in (
                "recommendation",
                "hierarchy",
                "naming_hierarchy",
                "growth_path",
                "wf1_context_used",
                "bpa_context_used",
                "execution_time_ms",
            ):
                value = brand_architecture_data.get(key)
                if value is not None:
                    result_data[key] = value
            # Copy strategy as arch_strategy to avoid collision with BPA strategy
            arch_strategy = brand_architecture_data.get("strategy")
            if arch_strategy:
                result_data["arch_strategy"] = arch_strategy
            baa_conf = brand_architecture_data.get("confidence_score")
            if baa_conf is not None:
                confidence_scores["brand_architecture"] = baa_conf
            # Build a richer summary from BAA data
            rec = brand_architecture_data.get("recommendation", {})
            model = rec.get("recommended_model", "")
            hierarchy = brand_architecture_data.get("hierarchy", {})
            depth = hierarchy.get("total_depth", 0)
            nodes = hierarchy.get("total_nodes", 0)
            if model:
                model_label = model.replace("_", " ").title()
                result_data["summary"] = (
                    f"Brand architecture strategy generated. "
                    f"Recommended model: **{model_label}** "
                    f"({nodes} brand entities, {depth} levels deep). "
                    f"Confidence: {baa_conf or 0:.0%}"
                )
            # Merge BAA sources with existing
            baa_sources = brand_architecture_data.get("sources", [])
            if baa_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in baa_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = baa_sources

        # Promote brand personality fields to top-level result_data
        if brand_personality_data:
            for key in (
                "aaker_profile",
                "archetype",
                "values_hierarchy",
                "emotional_map",
                "voice_matrix",
                "character_brief",
                "wf1_context_used",
                "bpa_context_used",
                "baa_context_used",
                "execution_time_ms",
                "sub_brand_constraint_applied",
            ):
                value = brand_personality_data.get(key)
                if value is not None:
                    result_data[key] = value
            bpv_conf = brand_personality_data.get("confidence_score")
            if bpv_conf is not None:
                confidence_scores["brand_personality"] = bpv_conf
            # Build a richer summary from BPV data
            aaker = brand_personality_data.get("aaker_profile", {})
            primary_dim = (
                aaker.get("primary_dimension", "") if isinstance(aaker, dict) else ""
            )
            arch = brand_personality_data.get("archetype", {})
            raw_primary = arch.get("primary", {}) if isinstance(arch, dict) else {}
            primary_arch = (
                raw_primary.get("name", "")
                if isinstance(raw_primary, dict)
                else str(raw_primary) if raw_primary else ""
            )
            if primary_dim and primary_arch:
                result_data["summary"] = (
                    f"Brand personality designed. "
                    f"Primary dimension: **{primary_dim}**, "
                    f"Primary archetype: **{primary_arch}**. "
                    f"Confidence: {bpv_conf or 0:.0%}"
                )
            # Merge BPV sources with existing
            bpv_sources = brand_personality_data.get("sources", [])
            if bpv_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in bpv_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = bpv_sources

        # Promote brand naming & tagline fields to top-level result_data
        if brand_naming_data:
            for key in (
                "name_candidates",
                "shortlisted_names",
                "taglines",
                "naming_brief",
                "availability_results",
                "scoring_summary",
                "wf1_context_used",
                "bpa_context_used",
                "bpv_context_used",
                "baa_context_used",
                "execution_time_ms",
            ):
                value = brand_naming_data.get(key)
                if value is not None:
                    result_data[key] = value
            nta_conf = brand_naming_data.get("confidence_score")
            if nta_conf is not None:
                confidence_scores["brand_naming"] = nta_conf
            # Build richer summary from NTA data
            candidates = brand_naming_data.get("name_candidates", [])
            candidates_count = len(candidates)
            top_name = ""
            if candidates and isinstance(candidates[0], dict):
                top_name = candidates[0].get("name", "")
            if top_name:
                result_data["summary"] = (
                    f"Brand naming complete. {candidates_count} candidates generated. "
                    f"Top recommendation: **{top_name}**. "
                    f"Confidence: {nta_conf or 0:.0%}"
                )
            # Merge NTA sources with existing
            nta_sources = brand_naming_data.get("sources", [])
            if nta_sources:
                existing_sources = result_data.get("sources", [])
                if isinstance(existing_sources, list):
                    existing_urls = {
                        s.get("url") for s in existing_sources if isinstance(s, dict)
                    }
                    for src in nta_sources:
                        if (
                            isinstance(src, dict)
                            and src.get("url") not in existing_urls
                        ):
                            existing_sources.append(src)
                    result_data["sources"] = existing_sources
                else:
                    result_data["sources"] = nta_sources

        # Promote brand story & narrative fields to top-level result_data
        if brand_story_data:
            for key in (
                "origin_story",
                "mission_vision",
                "pitches",
                "channel_narratives",
                "story_style_guide",
                "subbrand_stories",
                "narrative_package",
                "wf2_strategy_summary",
                "execution_time_ms",
            ):
                value = brand_story_data.get(key)
                if value is not None:
                    result_data[key] = value
            bsa_conf = brand_story_data.get("confidence_score")
            if bsa_conf is not None:
                confidence_scores["brand_story"] = bsa_conf
            # Build richer summary from BSA data
            narrative_pkg = brand_story_data.get("narrative_package", {})
            narrative_dna = narrative_pkg.get("narrative_dna", "")
            if narrative_dna:
                result_data["summary"] = (
                    f"Brand story complete. "
                    f"Narrative DNA: {narrative_dna} "
                    f"Confidence: {bsa_conf or 0:.0%}"
                )
            # GCS URI
            gcs_uri = brand_story_data.get("gcs_uri", "")
            if gcs_uri:
                result_data["gcs_uri"] = gcs_uri

        # Promote campaign architecture fields to top-level result_data
        if campaign_arch_data:
            for key in (
                "blueprint",
                "funnel_map",
                "targeting_specs",
                "placement_budget",
                "test_plan",
                "kpi_targets",
                "performance_projections",
                "risk_assessment",
                "creative_briefs",
                "special_ad_category",
                "meta_api_compatible",
                "execution_time_ms",
            ):
                value = campaign_arch_data.get(key)
                if value is not None:
                    result_data[key] = value
            caa_conf = campaign_arch_data.get("confidence_score")
            if caa_conf is not None:
                confidence_scores["campaign_architecture"] = caa_conf
            # Build richer summary from CAA data
            bp = campaign_arch_data.get("blueprint", {})
            campaign_name = bp.get("campaign_name", "")
            if campaign_name:
                result_data["summary"] = (
                    f"Campaign architecture complete. "
                    f"Blueprint: {campaign_name}. "
                    f"Confidence: {caa_conf or 0:.0%}"
                )
            caa_gcs = campaign_arch_data.get("gcs_uri", "")
            if caa_gcs:
                result_data["gcs_uri"] = caa_gcs

        # Store per-agent confidence scores and compute average
        if confidence_scores:
            result_data["confidence_scores"] = confidence_scores
            result_data["confidence_score"] = round(
                sum(confidence_scores.values()) / len(confidence_scores), 2
            )

        # Populate score from BSI (used by BrandEquityDashboard)
        if bsi_data:
            result_data["score"] = bsi_data.get("score", 0)
            # Extract pillar scores for dashboard gauges
            pillars = bsi_data.get("pillars", [])
            for pillar in pillars:
                if isinstance(pillar, dict):
                    name = pillar.get("name", "").lower()
                    pillar_score = pillar.get("score")
                    if pillar_score is not None:
                        if "financial" in name:
                            result_data["financials"] = pillar_score
                        elif "behavioral" in name or "awareness" in name:
                            result_data["awareness"] = pillar_score
                        elif "legal" in name:
                            # Maps ISO 10668 Legal pillar to the "sentiment"
                            # gauge on the BrandEquityDashboard frontend
                            # component for backward compatibility.
                            result_data["sentiment"] = pillar_score
        else:
            result_data["score"] = 0

        # Include valuation data if available
        if valuation_data:
            result_data["valuation"] = valuation_data

        # Generate UI schema hints when manifest-ui-mapper skill is active
        skill_context = self.config.get("skill_context", "") if self.config else ""
        if skill_context:
            result_data["ui_schema"] = self._build_ui_schema(
                outputs, bsi_data, valuation_data
            )

        return {"result_data": result_data}

    @staticmethod
    def _build_ui_schema(
        outputs: dict[str, Any],
        bsi_data: dict[str, Any] | None,
        valuation_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build a UI schema object based on available pipeline results.

        Tells the frontend which charts and visualizations to render.
        """
        charts: list[dict[str, str]] = []

        # Check for market research data
        has_market_research = any(
            isinstance(o, dict) and o.get("market_sizing") for o in outputs.values()
        )

        # Check for competitor intelligence data
        has_competitor_intel = any(
            isinstance(o, dict) and (o.get("competitors") or o.get("competitor_matrix"))
            for o in outputs.values()
        )

        # Check for audience persona data
        has_audience_persona = any(
            isinstance(o, dict) and o.get("personas") for o in outputs.values()
        )

        # Check for trend/cultural insights data
        has_trend_cultural = any(
            isinstance(o, dict) and (o.get("scored_trends") or o.get("trend_report"))
            for o in outputs.values()
        )

        # Check for voice of customer data
        has_voice_of_customer = any(
            isinstance(o, dict)
            and (
                o.get("voc_health_score") is not None
                or o.get("themes")
                or o.get("pain_point_priority_matrix")
            )
            for o in outputs.values()
        )

        # Check for brand positioning data
        has_brand_positioning = any(
            isinstance(o, dict)
            and (
                o.get("recommended_positioning")
                or o.get("positioning_candidates")
                or o.get("perceptual_maps")
            )
            for o in outputs.values()
        )

        # Check for brand architecture data
        has_brand_architecture = any(
            isinstance(o, dict)
            and o.get("recommendation", {}).get("recommended_model")
            and o.get("hierarchy", {}).get("root")
            for o in outputs.values()
        )

        # Check for brand personality data
        has_brand_personality = any(
            isinstance(o, dict)
            and (
                o.get("aaker_profile", {}).get("dimensions")
                or o.get("archetype", {}).get("primary")
            )
            for o in outputs.values()
        )

        # Brand equity / valuation pipeline
        if bsi_data:
            charts.append(
                {
                    "type": "radar_chart",
                    "data_key": "bsi.pillars",
                    "label": "Brand Strength Pillars",
                }
            )
            charts.append(
                {
                    "type": "score_gauge",
                    "data_key": "score",
                    "max": "100",
                    "label": "Overall BSI Score",
                }
            )
        if valuation_data:
            charts.append(
                {
                    "type": "valuation_card",
                    "data_key": "valuation.brand_value_npv",
                    "label": "Brand Value",
                }
            )

        # Content pipeline
        has_blog = any(
            isinstance(o, dict) and "blog_content" in o for o in outputs.values()
        )
        has_social = any(
            isinstance(o, dict) and "adapted_posts" in o for o in outputs.values()
        )
        if has_blog:
            charts.append({"type": "word_count_badge", "data_key": "word_count"})
            charts.append({"type": "seo_score_card", "data_key": "seo_meta"})
        if has_social:
            charts.append({"type": "platform_cards", "data_key": "adapted_posts"})

        # Determine dashboard type
        if bsi_data or valuation_data:
            schema_type = "brand_equity_dashboard"
        elif has_brand_architecture:
            schema_type = "brand_architecture_dashboard"
            charts.append(
                {
                    "type": "architecture_recommendation",
                    "data_key": "recommendation",
                }
            )
            charts.append({"type": "brand_hierarchy_tree", "data_key": "hierarchy"})
            charts.append({"type": "naming_hierarchy", "data_key": "naming_hierarchy"})
            charts.append({"type": "growth_roadmap", "data_key": "growth_path"})
            charts.append({"type": "strategy_overview", "data_key": "arch_strategy"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_brand_personality:
            schema_type = "brand_personality_dashboard"
            charts.append({"type": "aaker_radar", "data_key": "aaker_profile"})
            charts.append({"type": "archetype_cards", "data_key": "archetype"})
            charts.append({"type": "values_hierarchy", "data_key": "values_hierarchy"})
            charts.append({"type": "emotional_map", "data_key": "emotional_map"})
            charts.append({"type": "voice_matrix", "data_key": "voice_matrix"})
            charts.append({"type": "character_brief", "data_key": "character_brief"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_brand_positioning:
            schema_type = "brand_positioning_dashboard"
            charts.append(
                {
                    "type": "positioning_statement",
                    "data_key": "recommended_positioning",
                }
            )
            charts.append(
                {
                    "type": "positioning_candidates",
                    "data_key": "positioning_candidates",
                }
            )
            charts.append({"type": "value_proposition_canvas", "data_key": "canvas"})
            charts.append({"type": "perceptual_maps", "data_key": "perceptual_maps"})
            charts.append(
                {"type": "differentiation_framework", "data_key": "differentiation"}
            )
            charts.append({"type": "strategy_overview", "data_key": "strategy"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_audience_persona:
            # Frontend renders APA via data-key detection (personas, journey_maps),
            # not ui_schema.type. This hint is for future programmatic consumers.
            schema_type = "audience_persona_dashboard"
            charts.append({"type": "persona_cards", "data_key": "personas"})
            charts.append({"type": "journey_timelines", "data_key": "journey_maps"})
            charts.append({"type": "segment_matrix", "data_key": "segment_matrix"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_trend_cultural:
            schema_type = "trend_cultural_dashboard"
            charts.append({"type": "trend_scorecard", "data_key": "scored_trends"})
            charts.append(
                {"type": "trend_persona_matrix", "data_key": "trend_persona_matrix"}
            )
            charts.append(
                {"type": "opportunity_alerts", "data_key": "opportunity_alerts"}
            )
            charts.append({"type": "cultural_shifts", "data_key": "cultural_shifts"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_voice_of_customer:
            schema_type = "voice_of_customer_dashboard"
            charts.append({"type": "voc_health_score", "data_key": "voc_health_score"})
            charts.append({"type": "sentiment_analysis", "data_key": "sentiment"})
            charts.append({"type": "theme_clusters", "data_key": "themes"})
            charts.append({"type": "nps_analysis", "data_key": "nps_analysis"})
            charts.append(
                {
                    "type": "pain_point_matrix",
                    "data_key": "pain_point_priority_matrix",
                }
            )
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_competitor_intel:
            schema_type = "competitor_intelligence_dashboard"
            charts.append(
                {"type": "competitor_matrix", "data_key": "competitor_matrix"}
            )
            charts.append({"type": "swot_analyses", "data_key": "swot_analyses"})
            charts.append({"type": "positioning_gaps", "data_key": "positioning_gaps"})
            charts.append(
                {"type": "benchmarking_report", "data_key": "benchmarking_report"}
            )
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_market_research:
            schema_type = "market_research_dashboard"
            charts.append({"type": "market_sizing_cards", "data_key": "market_sizing"})
            charts.append(
                {
                    "type": "competitive_landscape_table",
                    "data_key": "competitive_landscape",
                }
            )
            charts.append(
                {"type": "industry_trends_list", "data_key": "industry_trends"}
            )
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_blog or has_social:
            schema_type = "content_dashboard"
        elif any(isinstance(o, dict) and o.get("sources") for o in outputs.values()):
            schema_type = "research_dashboard"
            charts.append({"type": "findings_list", "data_key": "findings"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        else:
            schema_type = "generic_result"
            charts.append({"type": "findings_list", "data_key": "findings"})
            charts.append(
                {"type": "recommendations_list", "data_key": "recommendations"}
            )

        return {"type": schema_type, "charts": charts}

    @staticmethod
    def _extract_bsi(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract BSI data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                bsi = output.get("bsi")
                if isinstance(bsi, dict) and "score" in bsi:
                    return bsi
        return None

    @staticmethod
    def _extract_valuation(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract valuation data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                val = output.get("valuation")
                if isinstance(val, dict) and "brand_value_npv" in val:
                    return val
        return None

    @staticmethod
    def _extract_market_research(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract market research data from any node output.

        Looks for outputs containing market_sizing or market_overview,
        which are produced by the market-research-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("market_sizing") or output.get("market_overview"):
                    return output
        return None

    @staticmethod
    def _extract_competitor_intelligence(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract competitor intelligence data from any node output.

        Looks for outputs containing competitors or competitor_matrix,
        which are produced by the competitor-intel-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("competitors") or output.get("competitor_matrix"):
                    return output
        return None

    @staticmethod
    def _extract_audience_persona(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract audience persona data from any node output.

        Looks for outputs containing personas or journey_maps,
        which are produced by the audience-persona-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("personas") or output.get("journey_maps"):
                    return output
        return None

    @staticmethod
    def _extract_trend_cultural(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract trend/cultural insights data from any node output.

        Looks for outputs containing scored_trends or trend_report,
        which are produced by the trend-cultural-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("scored_trends") or output.get("trend_report"):
                    return output
        return None

    @staticmethod
    def _extract_voice_of_customer(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract voice of customer data from any node output.

        Looks for outputs containing voc_health_score or sentiment analysis,
        which are produced by the voc-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if (
                    output.get("voc_health_score") is not None
                    or output.get("themes")
                    or output.get("pain_point_priority_matrix")
                ):
                    return output
        return None

    @staticmethod
    def _extract_brand_positioning(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract brand positioning data from any node output.

        Looks for outputs containing recommended_positioning or
        positioning_candidates, which are produced by
        brand-positioning-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("recommended_positioning") or output.get(
                    "positioning_candidates"
                ):
                    return output
        return None

    @staticmethod
    def _extract_brand_personality(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract brand personality data from any node output.

        Looks for outputs containing aaker_profile AND archetype keys,
        which are produced by brand-personality-agent-svc.
        Accepts empty dicts (error/prerequisite-failure responses)
        so the frontend can display the error findings.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if "aaker_profile" in output and "archetype" in output:
                    return output
        return None

    @staticmethod
    def _extract_brand_naming(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract brand naming data from any node output.

        Looks for outputs containing name_candidates AND naming_brief keys,
        which are produced by brand-naming-agent-svc.
        Accepts empty dicts (error/prerequisite-failure responses)
        so the frontend can display the error findings.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if "name_candidates" in output and "naming_brief" in output:
                    return output
        return None

    @staticmethod
    def _extract_brand_story(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract brand story data from any node output.

        Looks for outputs containing origin_story AND narrative_package keys,
        which are produced by brand-story-agent-svc.
        Accepts empty dicts (error/prerequisite-failure responses)
        so the frontend can display the error findings.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if "origin_story" in output and "narrative_package" in output:
                    return output
        return None

    @staticmethod
    def _extract_brand_architecture(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract brand architecture data from any node output.

        Looks for outputs containing recommendation with recommended_model
        and hierarchy with root, which are produced by
        brand-architecture-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                rec = output.get("recommendation")
                hier = output.get("hierarchy")
                if (
                    isinstance(rec, dict)
                    and rec.get("recommended_model")
                    and isinstance(hier, dict)
                    and hier.get("root")
                ):
                    return output
        return None

    @staticmethod
    def _extract_campaign_architecture(
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract campaign architecture data from any node output.

        Looks for outputs containing blueprint OR funnel_map OR
        targeting_specs keys, which are produced by
        campaign-architecture-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if (
                    "blueprint" in output
                    or "funnel_map" in output
                    or "targeting_specs" in output
                ):
                    return output
        return None
