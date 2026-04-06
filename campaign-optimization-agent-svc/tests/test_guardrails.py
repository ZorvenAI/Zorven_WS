"""Tests for the 3-layer guardrail system (Input/Decision/Output).

Tests all 24 named rules: IG-01..08, PG-01..10, OG-01..06.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.logic.guardrails import (
    DecisionGuardrails,
    GuardrailAction,
    GuardrailReport,
    GuardrailResult,
    InputGuardrails,
    OutputGuardrails,
)


# ── Helpers ──────────────────────────────────────────────────────


def _make_settings(**overrides):
    """Create a mock settings object with sensible defaults."""
    s = MagicMock()
    s.MIN_SPEND_BEFORE_DECISION_USD = overrides.get("min_spend", 50.0)
    s.MIN_IMPRESSIONS_BEFORE_DECISION = overrides.get("min_impressions", 1000)
    s.OPTIMIZATION_COOLDOWN_HOURS = overrides.get("cooldown_hours", 24)
    s.MAX_AUTO_ACTIONS_PER_DAY = overrides.get("max_actions", 10)
    s.MAX_DAILY_BUDGET_INCREASE_PCT = overrides.get("max_increase", 20)
    s.MAX_DAILY_BUDGET_DECREASE_PCT = overrides.get("max_decrease", 50)
    s.REQUIRE_APPROVAL_ABOVE_USD = overrides.get("approval_threshold", 500.0)
    s.CAMPAIGN_LEVEL_ALWAYS_MANUAL = overrides.get("campaign_manual", True)
    return s


def _old_campaign():
    """Campaign that passes all input guardrails."""
    return {
        "campaign_id": "camp_001",
        "meta_access_token": "token_abc",
        "meta_ad_account_id": "act_123",
        "total_spend_usd": 500.0,
        "total_impressions": 50000,
        "created_at": (
            datetime.now(timezone.utc) - timedelta(days=10)
        ).isoformat(),
        "last_optimized_at": "",
        "daily_action_count": 0,
        "sandbox_mode": True,
        "optimization_count": 3,
        "active_ad_set_count": 3,
    }


# ── GuardrailReport properties ──────────────────────────────────


class TestGuardrailReport:
    def test_all_passed_true(self):
        report = GuardrailReport(
            results=[
                GuardrailResult(passed=True, rule_id="X", message="ok"),
                GuardrailResult(passed=True, rule_id="Y", message="ok"),
            ]
        )
        assert report.all_passed is True
        assert report.blocked is False
        assert report.failures == []

    def test_all_passed_false(self):
        report = GuardrailReport(
            results=[
                GuardrailResult(passed=True, rule_id="X", message="ok"),
                GuardrailResult(
                    passed=False,
                    rule_id="Y",
                    message="fail",
                    action=GuardrailAction.WARN,
                ),
            ]
        )
        assert report.all_passed is False

    def test_blocked_true(self):
        report = GuardrailReport(
            results=[
                GuardrailResult(
                    passed=False,
                    rule_id="Y",
                    message="blocked",
                    action=GuardrailAction.BLOCK,
                ),
            ]
        )
        assert report.blocked is True

    def test_failures_list(self):
        report = GuardrailReport(
            results=[
                GuardrailResult(passed=True, rule_id="X", message="ok"),
                GuardrailResult(passed=False, rule_id="Y", message="fail"),
            ]
        )
        assert len(report.failures) == 1
        assert report.failures[0].rule_id == "Y"


# ── Input Guardrails (IG-01 through IG-08) ──────────────────────


class TestInputGuardrails:
    def setup_method(self):
        self.ig = InputGuardrails()
        self.settings = _make_settings()

    def test_ig01_pass_valid_campaign_id(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig01 = [r for r in report.results if r.rule_id == "IG-01"][0]
        assert ig01.passed is True

    def test_ig01_fail_empty_campaign_id(self):
        campaign = _old_campaign()
        campaign["campaign_id"] = ""
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig01 = [r for r in report.results if r.rule_id == "IG-01"][0]
        assert ig01.passed is False
        assert ig01.action == GuardrailAction.SKIP

    def test_ig02_pass_valid_credentials(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig02 = [r for r in report.results if r.rule_id == "IG-02"][0]
        assert ig02.passed is True

    def test_ig02_fail_missing_token(self):
        campaign = _old_campaign()
        campaign["meta_access_token"] = ""
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig02 = [r for r in report.results if r.rule_id == "IG-02"][0]
        assert ig02.passed is False

    def test_ig02_fail_missing_ad_account(self):
        campaign = _old_campaign()
        campaign["meta_ad_account_id"] = ""
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig02 = [r for r in report.results if r.rule_id == "IG-02"][0]
        assert ig02.passed is False

    def test_ig03_pass_sufficient_data(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig03 = [r for r in report.results if r.rule_id == "IG-03"][0]
        assert ig03.passed is True

    def test_ig03_fail_low_spend(self):
        campaign = _old_campaign()
        campaign["total_spend_usd"] = 10.0
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig03 = [r for r in report.results if r.rule_id == "IG-03"][0]
        assert ig03.passed is False

    def test_ig03_fail_low_impressions(self):
        campaign = _old_campaign()
        campaign["total_impressions"] = 100
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig03 = [r for r in report.results if r.rule_id == "IG-03"][0]
        assert ig03.passed is False

    def test_ig04_pass_old_campaign(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig04 = [r for r in report.results if r.rule_id == "IG-04"][0]
        assert ig04.passed is True

    def test_ig04_fail_young_campaign(self):
        campaign = _old_campaign()
        campaign["created_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=12)
        ).isoformat()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig04 = [r for r in report.results if r.rule_id == "IG-04"][0]
        assert ig04.passed is False

    def test_ig04_fail_no_created_at(self):
        campaign = _old_campaign()
        campaign["created_at"] = ""
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig04 = [r for r in report.results if r.rule_id == "IG-04"][0]
        assert ig04.passed is False

    def test_ig04_fail_invalid_timestamp(self):
        campaign = _old_campaign()
        campaign["created_at"] = "not-a-date"
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig04 = [r for r in report.results if r.rule_id == "IG-04"][0]
        assert ig04.passed is False

    def test_ig05_pass_first_run(self):
        campaign = _old_campaign()
        campaign["last_optimized_at"] = ""
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig05 = [r for r in report.results if r.rule_id == "IG-05"][0]
        assert ig05.passed is True

    def test_ig05_pass_cooldown_expired(self):
        campaign = _old_campaign()
        campaign["last_optimized_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        ).isoformat()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig05 = [r for r in report.results if r.rule_id == "IG-05"][0]
        assert ig05.passed is True

    def test_ig05_fail_within_cooldown(self):
        campaign = _old_campaign()
        campaign["last_optimized_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=6)
        ).isoformat()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig05 = [r for r in report.results if r.rule_id == "IG-05"][0]
        assert ig05.passed is False

    def test_ig06_pass_under_limit(self):
        campaign = _old_campaign()
        campaign["daily_action_count"] = 5
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig06 = [r for r in report.results if r.rule_id == "IG-06"][0]
        assert ig06.passed is True

    def test_ig06_fail_at_limit(self):
        campaign = _old_campaign()
        campaign["daily_action_count"] = 10
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig06 = [r for r in report.results if r.rule_id == "IG-06"][0]
        assert ig06.passed is False
        assert ig06.action == GuardrailAction.BLOCK

    def test_ig07_always_passes(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig07 = [r for r in report.results if r.rule_id == "IG-07"][0]
        assert ig07.passed is True

    def test_ig07_sandbox_mode_message(self):
        campaign = _old_campaign()
        campaign["sandbox_mode"] = True
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig07 = [r for r in report.results if r.rule_id == "IG-07"][0]
        assert "ON" in ig07.message

    def test_ig07_production_mode_message(self):
        campaign = _old_campaign()
        campaign["sandbox_mode"] = False
        report = self.ig.check(campaign, {"key": "val"}, settings=self.settings)
        ig07 = [r for r in report.results if r.rule_id == "IG-07"][0]
        assert "PRODUCTION" in ig07.message

    def test_ig08_pass_tenant_config_present(self):
        campaign = _old_campaign()
        report = self.ig.check(
            campaign, {"cpa_target": 25.0}, settings=self.settings
        )
        ig08 = [r for r in report.results if r.rule_id == "IG-08"][0]
        assert ig08.passed is True

    def test_ig08_fail_empty_tenant_config(self):
        campaign = _old_campaign()
        report = self.ig.check(campaign, {}, settings=self.settings)
        ig08 = [r for r in report.results if r.rule_id == "IG-08"][0]
        assert ig08.passed is False
        assert ig08.action == GuardrailAction.WARN

    def test_all_pass_for_valid_campaign(self):
        """A fully valid campaign passes all 8 input guardrails."""
        campaign = _old_campaign()
        report = self.ig.check(
            campaign, {"cpa_target": 25.0}, settings=self.settings
        )
        assert report.all_passed is True
        assert len(report.results) == 8


# ── Decision Guardrails (PG-01 through PG-10) ───────────────────


class TestDecisionGuardrails:
    def setup_method(self):
        self.dg = DecisionGuardrails()
        self.settings = _make_settings()
        self.campaign = {
            "active_ad_set_count": 3,
            "optimization_count": 5,
        }

    def _base_rec(self, **overrides):
        rec = {
            "action_type": "adjust_budget",
            "entity_type": "ad_set",
            "entity_id": "adset_001",
            "current_values": {"daily_budget": 100},
            "proposed_values": {"daily_budget": 110},
            "reason": "",
        }
        rec.update(overrides)
        return rec

    def test_pg01_pass_within_increase_limit(self):
        rec = self._base_rec(
            current_values={"daily_budget": 100},
            proposed_values={"daily_budget": 120},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg01 = [r for r in report.results if r.rule_id == "PG-01"][0]
        assert pg01.passed is True

    def test_pg01_fail_excessive_increase(self):
        rec = self._base_rec(
            current_values={"daily_budget": 100},
            proposed_values={"daily_budget": 150},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg01 = [r for r in report.results if r.rule_id == "PG-01"][0]
        assert pg01.passed is False
        assert pg01.action == GuardrailAction.DOWNGRADE

    def test_pg01_fail_excessive_decrease(self):
        rec = self._base_rec(
            current_values={"daily_budget": 100},
            proposed_values={"daily_budget": 40},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg01 = [r for r in report.results if r.rule_id == "PG-01"][0]
        assert pg01.passed is False

    def test_pg01_pass_non_budget_action(self):
        rec = self._base_rec(action_type="pause", proposed_values={"status": "PAUSED"})
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg01 = [r for r in report.results if r.rule_id == "PG-01"][0]
        assert pg01.passed is True

    def test_pg02_pass_below_threshold(self):
        rec = self._base_rec(proposed_values={"daily_budget": 200})
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg02 = [r for r in report.results if r.rule_id == "PG-02"][0]
        assert pg02.passed is True

    def test_pg02_fail_above_threshold(self):
        rec = self._base_rec(proposed_values={"daily_budget": 600})
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg02 = [r for r in report.results if r.rule_id == "PG-02"][0]
        assert pg02.passed is False
        assert pg02.action == GuardrailAction.BLOCK

    def test_pg03_fail_campaign_level_always_manual(self):
        rec = self._base_rec(entity_type="campaign")
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg03 = [r for r in report.results if r.rule_id == "PG-03"][0]
        assert pg03.passed is False
        assert pg03.action == GuardrailAction.BLOCK

    def test_pg03_pass_ad_set_level(self):
        rec = self._base_rec(entity_type="ad_set")
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg03 = [r for r in report.results if r.rule_id == "PG-03"][0]
        assert pg03.passed is True

    def test_pg04_fail_last_active_ad_set(self):
        campaign = {"active_ad_set_count": 1, "optimization_count": 5}
        rec = self._base_rec(action_type="pause")
        report = self.dg.check(rec, campaign, settings=self.settings)
        pg04 = [r for r in report.results if r.rule_id == "PG-04"][0]
        assert pg04.passed is False
        assert pg04.action == GuardrailAction.BLOCK

    def test_pg04_pass_multiple_active(self):
        rec = self._base_rec(action_type="kill")
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg04 = [r for r in report.results if r.rule_id == "PG-04"][0]
        assert pg04.passed is True

    def test_pg05_fail_kill_low_conversions(self):
        rec = self._base_rec(
            action_type="kill",
            reason="high_cpa",
            current_values={"conversions": 5},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg05 = [r for r in report.results if r.rule_id == "PG-05"][0]
        assert pg05.passed is False

    def test_pg05_pass_kill_enough_conversions(self):
        rec = self._base_rec(
            action_type="kill",
            reason="high_cpa",
            current_values={"conversions": 15},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg05 = [r for r in report.results if r.rule_id == "PG-05"][0]
        assert pg05.passed is True

    def test_pg06_fail_imbalanced_reallocation(self):
        rec = self._base_rec(
            action_type="reallocate_budget",
            total_budget_before=1000,
            total_budget_after=1100,
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg06 = [r for r in report.results if r.rule_id == "PG-06"][0]
        assert pg06.passed is False

    def test_pg06_pass_balanced_reallocation(self):
        rec = self._base_rec(
            action_type="reallocate_budget",
            total_budget_before=1000,
            total_budget_after=1040,
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg06 = [r for r in report.results if r.rule_id == "PG-06"][0]
        assert pg06.passed is True

    def test_pg07_fail_creative_refresh_too_soon(self):
        recent = (
            datetime.now(timezone.utc) - timedelta(days=3)
        ).isoformat()
        rec = self._base_rec(
            action_type="creative_refresh",
            last_creative_refresh=recent,
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg07 = [r for r in report.results if r.rule_id == "PG-07"][0]
        assert pg07.passed is False

    def test_pg07_pass_creative_refresh_after_cooldown(self):
        old = (
            datetime.now(timezone.utc) - timedelta(days=10)
        ).isoformat()
        rec = self._base_rec(
            action_type="creative_refresh",
            last_creative_refresh=old,
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg07 = [r for r in report.results if r.rule_id == "PG-07"][0]
        assert pg07.passed is True

    def test_pg07_pass_no_previous_refresh(self):
        rec = self._base_rec(action_type="creative_refresh")
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg07 = [r for r in report.results if r.rule_id == "PG-07"][0]
        assert pg07.passed is True

    def test_pg08_fail_high_frequency_scale(self):
        rec = self._base_rec(
            action_type="scale",
            current_values={"frequency": 4.0},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg08 = [r for r in report.results if r.rule_id == "PG-08"][0]
        assert pg08.passed is False
        assert pg08.action == GuardrailAction.WARN

    def test_pg08_pass_acceptable_frequency(self):
        rec = self._base_rec(
            action_type="scale",
            current_values={"frequency": 2.0},
        )
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg08 = [r for r in report.results if r.rule_id == "PG-08"][0]
        assert pg08.passed is True

    def test_pg09_always_passes(self):
        rec = self._base_rec()
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg09 = [r for r in report.results if r.rule_id == "PG-09"][0]
        assert pg09.passed is True

    def test_pg10_fail_first_optimization(self):
        campaign = {"active_ad_set_count": 3, "optimization_count": 0}
        rec = self._base_rec()
        report = self.dg.check(rec, campaign, settings=self.settings)
        pg10 = [r for r in report.results if r.rule_id == "PG-10"][0]
        assert pg10.passed is False
        assert pg10.action == GuardrailAction.BLOCK

    def test_pg10_pass_subsequent_optimization(self):
        rec = self._base_rec()
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        pg10 = [r for r in report.results if r.rule_id == "PG-10"][0]
        assert pg10.passed is True

    def test_all_10_rules_present(self):
        """Every decision guardrail PG-01..10 is checked."""
        rec = self._base_rec()
        report = self.dg.check(rec, self.campaign, settings=self.settings)
        rule_ids = {r.rule_id for r in report.results}
        for i in range(1, 11):
            assert f"PG-{i:02d}" in rule_ids


# ── Output Guardrails (OG-01 through OG-06) ─────────────────────


class TestOutputGuardrails:
    def setup_method(self):
        self.og = OutputGuardrails()
        self.campaign = {"tenant_id": "tenant_001"}

    def _base_result(self, **overrides):
        result = {
            "verified": True,
            "spend_impact_pct": 10.0,
            "quality_score": 0.8,
            "tenant_id": "tenant_001",
            "data_age_hours": 2,
            "learnings_persisted": True,
        }
        result.update(overrides)
        return result

    def test_og01_pass_verified(self):
        report = self.og.check(self._base_result(), self.campaign)
        og01 = [r for r in report.results if r.rule_id == "OG-01"][0]
        assert og01.passed is True

    def test_og01_fail_not_verified(self):
        report = self.og.check(
            self._base_result(verified=False), self.campaign
        )
        og01 = [r for r in report.results if r.rule_id == "OG-01"][0]
        assert og01.passed is False
        assert og01.action == GuardrailAction.BLOCK

    def test_og02_pass_low_spend_impact(self):
        report = self.og.check(
            self._base_result(spend_impact_pct=15.0), self.campaign
        )
        og02 = [r for r in report.results if r.rule_id == "OG-02"][0]
        assert og02.passed is True

    def test_og02_fail_high_spend_impact(self):
        report = self.og.check(
            self._base_result(spend_impact_pct=35.0), self.campaign
        )
        og02 = [r for r in report.results if r.rule_id == "OG-02"][0]
        assert og02.passed is False
        assert og02.action == GuardrailAction.BLOCK

    def test_og03_pass_good_quality(self):
        report = self.og.check(
            self._base_result(quality_score=0.9), self.campaign
        )
        og03 = [r for r in report.results if r.rule_id == "OG-03"][0]
        assert og03.passed is True

    def test_og03_fail_low_quality(self):
        report = self.og.check(
            self._base_result(quality_score=0.3), self.campaign
        )
        og03 = [r for r in report.results if r.rule_id == "OG-03"][0]
        assert og03.passed is False
        assert og03.action == GuardrailAction.WARN

    def test_og04_pass_same_tenant(self):
        report = self.og.check(
            self._base_result(tenant_id="tenant_001"), self.campaign
        )
        og04 = [r for r in report.results if r.rule_id == "OG-04"][0]
        assert og04.passed is True

    def test_og04_fail_different_tenant(self):
        report = self.og.check(
            self._base_result(tenant_id="tenant_OTHER"), self.campaign
        )
        og04 = [r for r in report.results if r.rule_id == "OG-04"][0]
        assert og04.passed is False
        assert og04.action == GuardrailAction.BLOCK

    def test_og05_pass_fresh_data(self):
        report = self.og.check(
            self._base_result(data_age_hours=12), self.campaign
        )
        og05 = [r for r in report.results if r.rule_id == "OG-05"][0]
        assert og05.passed is True

    def test_og05_fail_stale_data(self):
        report = self.og.check(
            self._base_result(data_age_hours=30), self.campaign
        )
        og05 = [r for r in report.results if r.rule_id == "OG-05"][0]
        assert og05.passed is False
        assert og05.action == GuardrailAction.WARN

    def test_og06_pass_persisted(self):
        report = self.og.check(
            self._base_result(learnings_persisted=True), self.campaign
        )
        og06 = [r for r in report.results if r.rule_id == "OG-06"][0]
        assert og06.passed is True

    def test_og06_fail_not_persisted(self):
        report = self.og.check(
            self._base_result(learnings_persisted=False), self.campaign
        )
        og06 = [r for r in report.results if r.rule_id == "OG-06"][0]
        assert og06.passed is False

    def test_all_pass_valid_result(self):
        """A fully valid execution result passes all 6 output guardrails."""
        report = self.og.check(self._base_result(), self.campaign)
        assert report.all_passed is True
        assert len(report.results) == 6

    def test_all_6_rules_present(self):
        report = self.og.check(self._base_result(), self.campaign)
        rule_ids = {r.rule_id for r in report.results}
        for i in range(1, 7):
            assert f"OG-{i:02d}" in rule_ids
