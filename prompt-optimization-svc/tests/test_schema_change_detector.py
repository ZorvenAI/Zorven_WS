"""
US-056 Unit Tests — Schema Change Detector.

All tests use real SkillRegistryReader loading real skills.yaml files.
No mocks.
"""

from dataclasses import asdict
from pathlib import Path

import pytest

from app.kafka.schemas import SCHEMA_CHANGE_DETECTED, SchemaChangeEvent
from app.services.schema_change_detector import (
    SchemaChange,
    SchemaChangeDetector,
    SchemaChangeType,
)
from app.services.skill_registry_reader import (
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def reader():
    r = SkillRegistryReader(repo_root=REPO_ROOT)
    yield r
    r.clear_cache()


@pytest.fixture
def detector(reader):
    return SchemaChangeDetector(reader)


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


# ---------------------------------------------------------------------------
# detect_changes
# ---------------------------------------------------------------------------


class TestDetectChanges:
    def test_no_changes_returns_empty(self, detector):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", snapshot)
        assert changes == []

    def test_field_added_detected(self, detector):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        # Remove first field from snapshot to simulate it being new
        removed_field = snapshot.pop(0)
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", snapshot)
        added = [c for c in changes if c.change_type == SchemaChangeType.FIELD_ADDED]
        assert len(added) >= 1
        assert added[0].field_name == removed_field["field"]

    def test_length_changed_detected(self, detector, reader):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        # Find a field with max_length and change it
        for field_dict in snapshot:
            if field_dict.get("max_length") is not None:
                field_dict["max_length"] = field_dict["max_length"] + 999
                break
        else:
            pytest.skip("No fields with max_length in MRA synthesis")
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", snapshot)
        length_changes = [
            c for c in changes if c.change_type == SchemaChangeType.LENGTH_CHANGED
        ]
        assert len(length_changes) >= 1

    def test_required_changed_detected(self, detector):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        # Flip required on first field
        original_required = snapshot[0]["required"]
        snapshot[0]["required"] = not original_required
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", snapshot)
        req_changes = [
            c for c in changes if c.change_type == SchemaChangeType.REQUIRED_CHANGED
        ]
        assert len(req_changes) == 1
        assert req_changes[0].field_name == snapshot[0]["field"]
        assert req_changes[0].old_value == (not original_required)
        assert req_changes[0].new_value == original_required

    def test_multiple_changes_detected(self, detector):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        # Remove first field AND flip required on second
        snapshot.pop(0)
        if snapshot:
            snapshot[0]["required"] = not snapshot[0]["required"]
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", snapshot)
        assert len(changes) >= 2

    def test_unknown_prompt_returns_empty(self, detector):
        changes = detector.detect_changes("mra", "zorven-wf1-mra-nonexistent", [])
        assert changes == []

    def test_empty_snapshot_all_fields_added(self, detector, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", [])
        assert len(changes) == len(skill.output_schema)
        assert all(c.change_type == SchemaChangeType.FIELD_ADDED for c in changes)

    def test_change_contains_correct_metadata(self, detector):
        changes = detector.detect_changes("mra", "zorven-wf1-mra-synthesis", [])
        assert len(changes) > 0
        first = changes[0]
        assert "SKL-MRA" in first.skill_id
        assert first.prompt_name == "zorven-wf1-mra-synthesis"
        assert first.agent_code == "mra"
        assert first.detected_at  # ISO timestamp


# ---------------------------------------------------------------------------
# build_snapshot
# ---------------------------------------------------------------------------


class TestBuildSnapshot:
    def test_snapshot_for_known_prompt(self, detector):
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert snapshot is not None
        assert isinstance(snapshot, list)
        assert len(snapshot) > 0

    def test_snapshot_fields_match_schema(self, detector, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        assert len(snapshot) == len(skill.output_schema)

    def test_snapshot_for_unknown_returns_none(self, detector):
        result = detector.build_snapshot("mra", "zorven-wf1-mra-nonexistent")
        assert result is None

    def test_snapshot_includes_max_length(self, detector, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        for i, field in enumerate(skill.output_schema):
            assert snapshot[i]["max_length"] == field.max_length

    def test_snapshot_includes_required(self, detector, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        snapshot = detector.build_snapshot("mra", "zorven-wf1-mra-synthesis")
        for i, field in enumerate(skill.output_schema):
            assert snapshot[i]["required"] == field.required


# ---------------------------------------------------------------------------
# SchemaChange + SchemaChangeType
# ---------------------------------------------------------------------------


class TestSchemaChangeDataclass:
    def test_schema_change_fields(self):
        change = SchemaChange(
            change_type=SchemaChangeType.FIELD_ADDED,
            field_name="new_field",
            old_value=None,
            new_value={"type": "string"},
            skill_id="SKL-MRA-01",
            prompt_name="zorven-wf1-mra-synthesis",
            agent_code="mra",
            detected_at="2026-07-05T00:00:00+00:00",
        )
        assert change.change_type == SchemaChangeType.FIELD_ADDED
        assert change.field_name == "new_field"
        assert change.old_value is None
        d = asdict(change)
        assert "change_type" in d
        assert "detected_at" in d

    def test_schema_change_type_enum(self):
        assert len(SchemaChangeType) == 3
        assert SchemaChangeType.FIELD_ADDED.value == "FIELD_ADDED"
        assert SchemaChangeType.LENGTH_CHANGED.value == "LENGTH_CHANGED"
        assert SchemaChangeType.REQUIRED_CHANGED.value == "REQUIRED_CHANGED"


# ---------------------------------------------------------------------------
# SchemaChangeEvent
# ---------------------------------------------------------------------------


class TestSchemaChangeEvent:
    def test_event_has_correct_type(self):
        event = SchemaChangeEvent(
            prompt_name="zorven-wf1-mra-synthesis",
            agent_code="mra",
            skill_id="SKL-MRA-01",
            changes=[{"change_type": "FIELD_ADDED", "field_name": "test"}],
        )
        assert event.event_type == SCHEMA_CHANGE_DETECTED

    def test_event_serializable(self):
        event = SchemaChangeEvent(
            prompt_name="zorven-wf1-mra-synthesis",
            agent_code="mra",
            skill_id="SKL-MRA-01",
            changes=[{"change_type": "FIELD_ADDED", "field_name": "test"}],
        )
        d = event.model_dump()
        assert isinstance(d, dict)
        assert d["event_type"] == "prompt.schema_change_detected"
        assert d["prompt_name"] == "zorven-wf1-mra-synthesis"
        assert len(d["changes"]) == 1
        assert "correlation_id" in d
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# All 15 agents
# ---------------------------------------------------------------------------


class TestAllAgents:
    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_all_15_agents_snapshot_roundtrip(self, detector, reader, agent_code):
        """Build snapshot, then detect_changes with same → zero changes."""
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        snapshot = detector.build_snapshot(agent_code, prompt_name)
        if snapshot is not None:
            changes = detector.detect_changes(agent_code, prompt_name, snapshot)
            assert changes == [], f"False positive changes for {agent_code}: {changes}"
