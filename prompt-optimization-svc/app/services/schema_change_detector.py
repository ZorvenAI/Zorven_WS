"""Schema Change Detector — detect skill output_schema drift (US-056).

Compares current skill output_schema against a stored snapshot from the
latest PRODUCTION optimization run. Detects FIELD_ADDED, LENGTH_CHANGED,
and REQUIRED_CHANGED diffs so that preamble, baseline scorers, and golden
dataset expectations can be regenerated automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.registries.skill_definitions import SkillOutputField
from app.services.skill_registry_reader import SkillRegistryReader

logger = logging.getLogger(__name__)


class SchemaChangeType(str, Enum):
    """Types of output_schema changes detected between snapshots."""

    FIELD_ADDED = "FIELD_ADDED"
    LENGTH_CHANGED = "LENGTH_CHANGED"
    REQUIRED_CHANGED = "REQUIRED_CHANGED"


@dataclass
class SchemaChange:
    """A single detected schema change."""

    change_type: SchemaChangeType
    field_name: str
    old_value: Any
    new_value: Any
    skill_id: str
    prompt_name: str
    agent_code: str
    detected_at: str


class SchemaChangeDetector:
    """Compares current skill output_schema against stored snapshot.

    Detects FIELD_ADDED, LENGTH_CHANGED, REQUIRED_CHANGED diffs and
    returns a list of SchemaChange objects for further action.
    """

    def __init__(self, skill_registry_reader: SkillRegistryReader) -> None:
        self._reader = skill_registry_reader

    def detect_changes(
        self,
        agent_code: str,
        prompt_name: str,
        snapshot_fields: list[dict],
    ) -> list[SchemaChange]:
        """Compare current skill schema against snapshot.

        Args:
            agent_code: Agent code for skill lookup.
            prompt_name: Prompt name to resolve skill.
            snapshot_fields: Previous output_schema as list of dicts
                (from SchemaSnapshot.schema_json).

        Returns list of detected changes. Empty if no changes or
        if skill cannot be resolved.
        """
        skill = self._reader.get_skill_for_prompt(agent_code, prompt_name)
        if skill is None:
            return []

        return self._compare_fields(
            current_fields=skill.output_schema,
            snapshot_fields=snapshot_fields,
            skill_id=skill.skill_id,
            prompt_name=prompt_name,
            agent_code=agent_code,
        )

    def build_snapshot(
        self,
        agent_code: str,
        prompt_name: str,
    ) -> Optional[list[dict]]:
        """Build a snapshot of current skill output_schema.

        Returns list of field dicts suitable for storing in SchemaSnapshot,
        or None if skill cannot be resolved.
        """
        skill = self._reader.get_skill_for_prompt(agent_code, prompt_name)
        if skill is None:
            return None

        return [
            {
                "field": f.field,
                "type": f.type,
                "max_length": f.max_length,
                "required": f.required,
                "enum_values": f.enum_values,
            }
            for f in skill.output_schema
        ]

    def _compare_fields(
        self,
        current_fields: list[SkillOutputField],
        snapshot_fields: list[dict],
        skill_id: str,
        prompt_name: str,
        agent_code: str,
    ) -> list[SchemaChange]:
        """Field-by-field comparison producing change list."""
        now = datetime.now(timezone.utc).isoformat()
        snapshot_map: dict[str, dict] = {f["field"]: f for f in snapshot_fields}
        changes: list[SchemaChange] = []

        for field in current_fields:
            snap = snapshot_map.get(field.field)

            if snap is None:
                changes.append(
                    SchemaChange(
                        change_type=SchemaChangeType.FIELD_ADDED,
                        field_name=field.field,
                        old_value=None,
                        new_value={
                            "type": field.type,
                            "max_length": field.max_length,
                            "required": field.required,
                        },
                        skill_id=skill_id,
                        prompt_name=prompt_name,
                        agent_code=agent_code,
                        detected_at=now,
                    )
                )
                continue

            if field.max_length != snap.get("max_length"):
                changes.append(
                    SchemaChange(
                        change_type=SchemaChangeType.LENGTH_CHANGED,
                        field_name=field.field,
                        old_value=snap.get("max_length"),
                        new_value=field.max_length,
                        skill_id=skill_id,
                        prompt_name=prompt_name,
                        agent_code=agent_code,
                        detected_at=now,
                    )
                )

            if field.required != snap.get("required", True):
                changes.append(
                    SchemaChange(
                        change_type=SchemaChangeType.REQUIRED_CHANGED,
                        field_name=field.field,
                        old_value=snap.get("required", True),
                        new_value=field.required,
                        skill_id=skill_id,
                        prompt_name=prompt_name,
                        agent_code=agent_code,
                        detected_at=now,
                    )
                )

        return changes
