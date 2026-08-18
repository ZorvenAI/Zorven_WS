"""G-05 — Ad-hoc question detection.

Tests for the shared field map and speaker-tag gating logic. Integration
tests for the full detection pipeline live in test_session_state.py.
"""

from __future__ import annotations

import pytest

from app.logic.field_map import (
    DEFAULT_WORKFLOW_TARGET,
    FIELD_MAP,
    resolve_field,
    resolve_workflow_target,
)

pytestmark = pytest.mark.unit


# ── Field map resolution ───────────────────────────────────────────────


def test_resolve_field_known():
    """A known field returns the correct (target_field, workflow_target)."""
    field, wf = resolve_field("competitors")
    assert field == "competitors"
    assert wf == "WF2"


def test_resolve_field_wf1():
    field, wf = resolve_field("founded_year")
    assert field == "founded_year"
    assert wf == "WF1"


def test_resolve_field_wf3():
    field, wf = resolve_field("sales_channels")
    assert field == "sales_channels"
    assert wf == "WF3"


def test_resolve_field_unknown_defaults_to_wf1():
    """Unknown fields pass through with the default workflow target."""
    field, wf = resolve_field("favourite_colour")
    assert field == "favourite_colour"
    assert wf == DEFAULT_WORKFLOW_TARGET
    assert wf == "WF1"


def test_resolve_field_normalises_case():
    """Case and whitespace are normalised before lookup."""
    field, wf = resolve_field("Founded_Year")
    assert field == "founded_year"
    assert wf == "WF1"


def test_resolve_field_normalises_hyphens():
    """Hyphens are treated like underscores."""
    field, wf = resolve_field("brand-asset-status")
    assert field == "brand_asset_status"
    assert wf == "WF2"


def test_resolve_field_normalises_spaces():
    """Spaces are collapsed to underscores."""
    field, wf = resolve_field("marketing budget range")
    assert field == "marketing_budget_range"
    assert wf == "WF3"


def test_resolve_field_strips_whitespace():
    field, wf = resolve_field("  competitors  ")
    assert field == "competitors"
    assert wf == "WF2"


def test_resolve_field_empty_string():
    """An empty inferred_target_field doesn't crash."""
    field, wf = resolve_field("")
    assert wf == "WF1"


def test_resolve_workflow_target_for_notable():
    """suggested_field maps to workflow_target for notable facts."""
    assert resolve_workflow_target("retail_locations") == "WF3"
    assert resolve_workflow_target("competitors") == "WF2"
    assert resolve_workflow_target("mission") == "WF1"


def test_resolve_workflow_target_unknown():
    assert resolve_workflow_target("obscure_field") == "WF1"


def test_every_map_entry_is_valid():
    """Every value in FIELD_MAP is a valid workflow target."""
    valid = {"WF1", "WF2", "WF3"}
    for field, wf in FIELD_MAP.items():
        assert wf in valid, f"{field} maps to invalid {wf}"


def test_adhoc_resolves_target_field_via_map():
    """AC-3 named test: inferred_target_field resolves through field_map.

    The retail location example from AC-4 maps to WF3.
    """
    field, wf = resolve_field("retail_locations")
    assert field == "retail_locations"
    assert wf == "WF3"
