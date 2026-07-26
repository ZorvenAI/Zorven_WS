"""Tests for the graph builder — manifest to LangGraph compilation."""

import pytest

from app.factory.graph_builder import GraphBuilder, GraphBuildError

# ── Seed manifest structures (matching seed_manifests.py) ──


def _brand_analysis_manifest():
    return {
        "nodes": [
            {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
            {
                "id": "market_research",
                "type": "external",
                "url": "http://discovery-agent-svc:8020/v1/search",
                "config": {"focus": "market_trends,competitors"},
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
        "global_config": {"model": "gemini-3.5-flash", "temperature": 0.7},
    }


def _iso_brand_equity_manifest():
    return {
        "nodes": [
            {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
            {
                "id": "web_research",
                "type": "external",
                "url": "http://discovery-agent-svc:8020/v1/search",
                "config": {"focus": "royalty_rates,market_trends,brand_rankings"},
            },
            {
                "id": "valuation_logic",
                "type": "external",
                "url": "http://intelligence-agent-svc:8030/v1/iso-calc",
                "config": {"method": "royalty_relief", "horizon_years": 5},
            },
            {"id": "manager", "type": "internal", "handler": "ManagerNode"},
        ],
        "edges": [
            ["intent_router", "web_research"],
            ["web_research", "valuation_logic"],
            ["valuation_logic", "manager"],
        ],
        "global_config": {"model": "gemini-3.5-flash", "temperature": 0.3},
    }


def _competitor_audit_manifest():
    return {
        "nodes": [
            {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
            {
                "id": "competitor_research",
                "type": "external",
                "url": "http://discovery-agent-svc:8020/v1/search",
                "config": {"focus": "competitors,market_share"},
            },
            {
                "id": "gap_analyzer",
                "type": "external",
                "url": "http://intelligence-agent-svc:8030/v1/analyze",
                "config": {"analysis_type": "competitive_gap"},
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
        "global_config": {"model": "gemini-3.5-flash", "temperature": 0.5},
    }


def _content_strategy_manifest():
    return {
        "nodes": [
            {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
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
        "global_config": {"model": "gemini-3.5-flash", "temperature": 0.7},
    }


class TestGraphBuilderCompilation:
    """Test that all 4 seed manifests compile into valid graphs."""

    def test_compile_brand_analysis(self):
        graph = GraphBuilder.build(_brand_analysis_manifest())
        assert graph is not None

    def test_compile_iso_brand_equity(self):
        graph = GraphBuilder.build(_iso_brand_equity_manifest())
        assert graph is not None

    def test_compile_competitor_audit(self):
        graph = GraphBuilder.build(_competitor_audit_manifest())
        assert graph is not None

    def test_compile_content_strategy(self):
        graph = GraphBuilder.build(_content_strategy_manifest())
        assert graph is not None


class TestGraphBuilderErrors:
    """Test error handling for invalid manifests."""

    def test_empty_nodes_raises(self):
        with pytest.raises(GraphBuildError, match="no nodes"):
            GraphBuilder.build({"nodes": [], "edges": []})

    def test_unknown_handler_raises(self):
        manifest = {
            "nodes": [
                {"id": "n1", "type": "internal", "handler": "UnknownNode"},
            ],
            "edges": [],
        }
        with pytest.raises(ValueError, match="Unknown handler"):
            GraphBuilder.build(manifest)

    def test_cyclic_edges_raises(self):
        manifest = {
            "nodes": [
                {"id": "a", "type": "internal", "handler": "StrategyNode"},
                {"id": "b", "type": "internal", "handler": "ReportNode"},
            ],
            "edges": [["a", "b"], ["b", "a"]],
        }
        with pytest.raises(GraphBuildError, match="cycle"):
            GraphBuilder.build(manifest)

    def test_duplicate_node_id_raises(self):
        manifest = {
            "nodes": [
                {"id": "same", "type": "internal", "handler": "StrategyNode"},
                {"id": "same", "type": "internal", "handler": "ReportNode"},
            ],
            "edges": [],
        }
        with pytest.raises(GraphBuildError, match="Duplicate node ID"):
            GraphBuilder.build(manifest)

    def test_edge_references_unknown_node_raises(self):
        manifest = {
            "nodes": [
                {"id": "a", "type": "internal", "handler": "StrategyNode"},
            ],
            "edges": [["a", "nonexistent"]],
        }
        with pytest.raises(GraphBuildError, match="unknown"):
            GraphBuilder.build(manifest)

    def test_internal_node_missing_handler_raises(self):
        manifest = {
            "nodes": [
                {"id": "a", "type": "internal"},
            ],
            "edges": [],
        }
        with pytest.raises(GraphBuildError, match="missing 'handler'"):
            GraphBuilder.build(manifest)

    def test_external_node_missing_url_raises(self):
        manifest = {
            "nodes": [
                {"id": "a", "type": "external"},
            ],
            "edges": [],
        }
        with pytest.raises(GraphBuildError, match="missing 'url'"):
            GraphBuilder.build(manifest)

    def test_unknown_node_type_raises(self):
        manifest = {
            "nodes": [
                {"id": "a", "type": "quantum", "handler": "StrategyNode"},
            ],
            "edges": [],
        }
        with pytest.raises(GraphBuildError, match="Unknown node type"):
            GraphBuilder.build(manifest)
