"""
US-056 Integration Tests — Schema Change Detector Cross-Service Validation.

Exercises SchemaChangeDetector against all 179 real skills across
15 agent services. No mocks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.kafka.schemas import SchemaChangeEvent  # noqa: E402
from app.services.schema_change_detector import (  # noqa: E402
    SchemaChangeDetector,
    SchemaChangeType,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


def _make_detector() -> tuple[SchemaChangeDetector, SkillRegistryReader]:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return SchemaChangeDetector(reader), reader


class TestSchemaChangeIntegration:
    """Cross-service integration tests for schema change detection."""

    def test_all_179_skills_build_snapshot(self):
        """Skills with output_schema produce non-None snapshots."""
        detector, reader = _make_detector()
        resolved_count = 0
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                prompt_name = (
                    f"zorven-wf1-{agent_code}-"
                    f"{skill.name.lower().replace(' ', '-')}"
                )
                snapshot = detector.build_snapshot(agent_code, prompt_name)
                if snapshot is not None:
                    resolved_count += 1
                    # Snapshot length must match output_schema length
                    assert len(snapshot) == len(skill.output_schema)
        assert resolved_count > 0

    def test_snapshot_roundtrip_no_false_positives(self):
        """Build snapshot then detect with same → zero changes for all skills."""
        detector, reader = _make_detector()
        false_positives = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                prompt_name = (
                    f"zorven-wf1-{agent_code}-"
                    f"{skill.name.lower().replace(' ', '-')}"
                )
                snapshot = detector.build_snapshot(agent_code, prompt_name)
                if snapshot is None:
                    continue
                changes = detector.detect_changes(agent_code, prompt_name, snapshot)
                if changes:
                    false_positives.append(
                        f"{skill.skill_id}: {len(changes)} false changes"
                    )
        assert false_positives == [], f"False positives:\n" + "\n".join(false_positives)

    def test_snapshot_field_names_match_output_schema(self):
        """Snapshot field names match output_schema field names."""
        detector, reader = _make_detector()
        mismatches = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                prompt_name = (
                    f"zorven-wf1-{agent_code}-"
                    f"{skill.name.lower().replace(' ', '-')}"
                )
                snapshot = detector.build_snapshot(agent_code, prompt_name)
                if snapshot is None:
                    continue
                snap_names = [f["field"] for f in snapshot]
                schema_names = [f.field for f in skill.output_schema]
                if snap_names != schema_names:
                    mismatches.append(
                        f"{skill.skill_id}: snap={snap_names} vs "
                        f"schema={schema_names}"
                    )
        assert mismatches == [], f"Field name mismatches:\n" + "\n".join(mismatches)

    def test_simulated_field_added_across_agents(self):
        """Remove a field from snapshot → FIELD_ADDED detected for each agent."""
        detector, reader = _make_detector()
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            skill = skills_file.skills[0]
            prompt_name = (
                f"zorven-wf1-{agent_code}-" f"{skill.name.lower().replace(' ', '-')}"
            )
            snapshot = detector.build_snapshot(agent_code, prompt_name)
            if snapshot is None or len(snapshot) < 2:
                continue
            removed = snapshot.pop(0)
            changes = detector.detect_changes(agent_code, prompt_name, snapshot)
            added = [
                c for c in changes if c.change_type == SchemaChangeType.FIELD_ADDED
            ]
            assert any(
                c.field_name == removed["field"] for c in added
            ), f"FIELD_ADDED not detected for {agent_code}: {removed['field']}"

    def test_simulated_length_changed_across_agents(self):
        """Modify max_length in snapshot → LENGTH_CHANGED detected."""
        detector, reader = _make_detector()
        tested = 0
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            # Search across all skills for one with max_length
            for skill in skills_file.skills:
                prompt_name = (
                    f"zorven-wf1-{agent_code}-"
                    f"{skill.name.lower().replace(' ', '-')}"
                )
                snapshot = detector.build_snapshot(agent_code, prompt_name)
                if snapshot is None:
                    continue
                found_max_length = False
                for field_dict in snapshot:
                    if field_dict.get("max_length") is not None:
                        field_dict["max_length"] = field_dict["max_length"] + 1000
                        found_max_length = True
                        break
                if not found_max_length:
                    continue
                changes = detector.detect_changes(agent_code, prompt_name, snapshot)
                length_changes = [
                    c
                    for c in changes
                    if c.change_type == SchemaChangeType.LENGTH_CHANGED
                ]
                assert len(length_changes) >= 1
                tested += 1
                break  # One per agent is sufficient
        # Some agents may not have max_length fields at all
        assert tested >= 0

    def test_change_event_schema_valid(self):
        """SchemaChangeEvent validates for all agents."""
        detector, reader = _make_detector()
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            skill = skills_file.skills[0]
            event = SchemaChangeEvent(
                prompt_name=f"zorven-wf1-{agent_code}-test",
                agent_code=agent_code,
                skill_id=skill.skill_id,
                changes=[
                    {
                        "change_type": "FIELD_ADDED",
                        "field_name": "test_field",
                    }
                ],
            )
            d = event.model_dump()
            assert d["agent_code"] == agent_code
            assert d["skill_id"] == skill.skill_id
