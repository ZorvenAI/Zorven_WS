"""
US-056 Property Tests — Schema Change Detector Hypothesis Tests.

Property-based tests for schema change detection guarantees.
No mocks — uses real skills.yaml files.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.services.schema_change_detector import (  # noqa: E402
    SchemaChangeDetector,
    SchemaChangeType,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())
valid_agent_codes = st.sampled_from(VALID_CODES)

# Arbitrary snapshot fields (may or may not match real schemas)
snapshot_fields = st.lists(
    st.fixed_dictionaries(
        {
            "field": st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
            "type": st.sampled_from(
                ["string", "integer", "array", "object", "boolean"]
            ),
            "max_length": st.one_of(
                st.none(), st.integers(min_value=1, max_value=10000)
            ),
            "required": st.booleans(),
            "enum_values": st.none(),
        }
    ),
    min_size=0,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSchemaChangeProperties:
    """Hypothesis property tests for schema change detection."""

    @given(agent_code=valid_agent_codes, fields=snapshot_fields)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_changes_never_raises(self, agent_code, fields):
        """detect_changes never raises, always returns list."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        detector = SchemaChangeDetector(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        result = detector.detect_changes(agent_code, prompt_name, fields)
        assert isinstance(result, list)

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_roundtrip_always_empty(self, agent_code):
        """build_snapshot then detect with same → always empty."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        detector = SchemaChangeDetector(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        snapshot = detector.build_snapshot(agent_code, prompt_name)
        if snapshot is not None:
            changes = detector.detect_changes(agent_code, prompt_name, snapshot)
            assert changes == []

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_field_removal_always_detected(self, agent_code):
        """Removing a field from snapshot → FIELD_ADDED in current."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        detector = SchemaChangeDetector(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        snapshot = detector.build_snapshot(agent_code, prompt_name)
        if snapshot is not None and len(snapshot) >= 2:
            removed = snapshot.pop(0)
            changes = detector.detect_changes(agent_code, prompt_name, snapshot)
            added_fields = [
                c.field_name
                for c in changes
                if c.change_type == SchemaChangeType.FIELD_ADDED
            ]
            assert removed["field"] in added_fields

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_change_count_bounded(self, agent_code):
        """Number of changes <= number of output fields."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        detector = SchemaChangeDetector(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        # Empty snapshot = worst case (all fields added)
        changes = detector.detect_changes(agent_code, prompt_name, [])
        # Each field can produce at most 1 FIELD_ADDED change
        assert len(changes) <= len(first_skill.output_schema)

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_detection_deterministic(self, agent_code):
        """Same inputs produce same output."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        detector = SchemaChangeDetector(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        prompt_name = (
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        )
        snapshot = detector.build_snapshot(agent_code, prompt_name)
        if snapshot is not None and len(snapshot) >= 2:
            modified = list(snapshot)
            modified.pop(0)
            c1 = detector.detect_changes(agent_code, prompt_name, modified)
            c2 = detector.detect_changes(agent_code, prompt_name, modified)
            assert len(c1) == len(c2)
            for a, b in zip(c1, c2):
                assert a.change_type == b.change_type
                assert a.field_name == b.field_name
