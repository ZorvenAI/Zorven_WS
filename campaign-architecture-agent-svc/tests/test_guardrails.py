"""Tests for CAA guardrails (Input, Plan, Output)."""

from unittest.mock import patch

import pytest

from app.logic.guardrails import InputGuardrails, OutputGuardrails, PlanGuardrails


class TestInputGuardrails:
    """Test IG-11 and IG-12."""

    def test_input_guardrails_budget_too_low(self):
        """Budget below Meta minimum ($10) is flagged."""
        ig = InputGuardrails()
        result = ig.check_budget_sanity(5.0)
        assert result["valid"] is False
        assert any("below" in i.lower() for i in result["issues"])

    def test_input_guardrails_budget_too_high(self):
        """Budget above configured cap is flagged."""
        ig = InputGuardrails()
        result = ig.check_budget_sanity(50000.0)
        assert result["valid"] is False
        assert any("exceeds" in i.lower() for i in result["issues"])

    def test_input_guardrails_special_ad_category_housing(self):
        """Housing keywords trigger HOUSING category."""
        ig = InputGuardrails()
        result = ig.detect_special_ad_category(
            {"industry": "real estate", "description": ""},
            "promote our apartment listings",
        )
        assert result == "HOUSING"

    def test_input_guardrails_special_ad_category_employment(self):
        """Employment keywords trigger EMPLOYMENT category."""
        ig = InputGuardrails()
        result = ig.detect_special_ad_category(
            {"industry": "staffing", "description": ""},
            "recruitment campaign",
        )
        assert result == "EMPLOYMENT"


class TestPlanGuardrails:
    """Test PG-06 and PG-07."""

    def test_plan_guardrails_budget_allocation_over_100(self):
        """Budget allocation summing to >101% is flagged."""
        pg = PlanGuardrails()
        funnel_map = {
            "stages": [
                {"stage": "tofu", "budget_pct": 50},
                {"stage": "mofu", "budget_pct": 40},
                {"stage": "bofu", "budget_pct": 20},
            ]
        }
        result = pg.check_budget_allocation(funnel_map)
        assert result["valid"] is False
        assert "110.0%" in result["issue"]

    def test_plan_guardrails_audience_overlap(self):
        """Audience overlap >50% between ad sets is flagged."""
        pg = PlanGuardrails()
        specs = [
            {
                "ad_set_name": "TOFU",
                "interests": ["tech", "saas", "cloud", "ai"],
            },
            {
                "ad_set_name": "MOFU",
                "interests": ["tech", "saas", "cloud", "marketing"],
            },
        ]
        result = pg.check_audience_overlap(specs)
        assert result["valid"] is False
        assert len(result["overlaps"]) > 0
        assert result["overlaps"][0]["overlap_pct"] > 50


class TestOutputGuardrails:
    """Test OG-06 and OG-08."""

    def test_output_guardrails_budget_cap_exceeded(self):
        """Ad set budgets exceeding campaign budget is flagged."""
        og = OutputGuardrails()
        blueprint = {
            "daily_budget": 100.0,
            "ad_sets": [
                {"daily_budget": 60.0},
                {"daily_budget": 60.0},
            ],
        }
        result = og.check_budget_cap(blueprint)
        assert result["valid"] is False
        assert "differ" in result["issue"].lower()

    def test_output_guardrails_valid_passes(self):
        """Valid blueprint passes all output guardrails."""
        og = OutputGuardrails()
        blueprint = {
            "campaign_objective": "AWARENESS",
            "daily_budget": 100.0,
            "ad_sets": [
                {
                    "name": "TOFU",
                    "objective": "AWARENESS",
                    "targeting": {"interests": ["tech"]},
                    "placements": ["facebook_feed"],
                    "daily_budget": 50.0,
                },
                {
                    "name": "MOFU",
                    "objective": "TRAFFIC",
                    "targeting": {"interests": ["saas"]},
                    "placements": ["instagram_feed"],
                    "daily_budget": 50.0,
                },
            ],
        }
        meta_result = og.check_meta_api_schema(blueprint)
        assert meta_result["valid"] is True
        assert meta_result["meta_api_compatible"] is True

        budget_result = og.check_budget_cap(blueprint)
        assert budget_result["valid"] is True
