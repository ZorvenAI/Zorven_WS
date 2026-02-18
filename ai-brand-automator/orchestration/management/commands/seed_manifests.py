"""
Management command to seed default pipeline manifests.

Idempotent — skips manifests that already exist (matched
on pipeline_id + version).  Safe to run on every deploy.
"""

from django.core.management.base import BaseCommand

from orchestration.models import PipelineManifest


class Command(BaseCommand):
    help = "Seed default pipeline manifests (idempotent)"

    MANIFESTS = [
        {
            "pipeline_id": "iso-brand-equity",
            "name": "ISO Brand Equity Valuation",
            "description": (
                "ISO 10668-compliant brand equity valuation "
                "using Royalty Relief method. Requires "
                "financial data (10-K) and performs web "
                "research for market benchmarks."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "web_research",
                        "type": "external",
                        "url": ("http://discovery-agent-svc" "/v1/search"),
                        "config": {
                            "focus": (
                                "royalty_rates," "market_trends," "brand_rankings"
                            ),
                        },
                    },
                    {
                        "id": "valuation_logic",
                        "type": "external",
                        "url": ("http://intelligence-agent-svc" "/v1/iso-calc"),
                        "config": {
                            "method": "royalty_relief",
                            "horizon_years": 5,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "web_research"],
                    ["web_research", "valuation_logic"],
                    ["valuation_logic", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "brand-analysis",
            "name": "Brand Analysis",
            "description": (
                "Analyze brand positioning, market fit, " "and growth opportunities"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": ("http://discovery-agent-svc" "/v1/search"),
                        "config": {
                            "focus": "market_trends,competitors",
                        },
                    },
                    {
                        "id": "brand_strategist",
                        "type": "internal",
                        "handler": "StrategyNode",
                    },
                    {
                        "id": "report_generator",
                        "type": "internal",
                        "handler": "ReportNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "brand_strategist"],
                    ["brand_strategist", "report_generator"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "competitor-audit",
            "name": "Competitor Audit",
            "description": (
                "Identify competitors, analyze gaps, "
                "and recommend differentiation strategies"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "competitor_research",
                        "type": "external",
                        "url": ("http://discovery-agent-svc" "/v1/search"),
                        "config": {
                            "focus": "competitors,market_share",
                        },
                    },
                    {
                        "id": "gap_analyzer",
                        "type": "external",
                        "url": ("http://intelligence-agent-svc" "/v1/analyze"),
                        "config": {
                            "analysis_type": "competitive_gap",
                        },
                    },
                    {
                        "id": "report_generator",
                        "type": "internal",
                        "handler": "ReportNode",
                    },
                ],
                "edges": [
                    ["intent_router", "competitor_research"],
                    ["competitor_research", "gap_analyzer"],
                    ["gap_analyzer", "report_generator"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "content-strategy",
            "name": "Content Strategy",
            "description": (
                "Generate content plans, audience analysis, " "and editorial calendars"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "audience_analyzer",
                        "type": "internal",
                        "handler": "AudienceNode",
                    },
                    {
                        "id": "content_planner",
                        "type": "internal",
                        "handler": "PlannerNode",
                    },
                    {
                        "id": "calendar_builder",
                        "type": "internal",
                        "handler": "CalendarNode",
                    },
                ],
                "edges": [
                    ["intent_router", "audience_analyzer"],
                    ["audience_analyzer", "content_planner"],
                    ["content_planner", "calendar_builder"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write("Seeding default pipeline manifests...")
        for manifest_cfg in self.MANIFESTS:
            obj, created = PipelineManifest.objects.get_or_create(
                pipeline_id=manifest_cfg["pipeline_id"],
                version=1,
                defaults={
                    "name": manifest_cfg["name"],
                    "description": manifest_cfg["description"],
                    "manifest_data": manifest_cfg["manifest_data"],
                    "tenant": None,  # Available to all tenants
                },
            )
            status = "Created" if created else "Already exists"
            self.stdout.write(f"  {status}: {obj.name}")
        self.stdout.write(self.style.SUCCESS("Pipeline manifest seeding complete."))
