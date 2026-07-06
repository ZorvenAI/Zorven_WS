"""OPT-12 Preamble Protection Validator (US-057).

Validates that GEPA mutations have not weakened or removed the schema
preamble from prompt templates. Detects missing markers, positional
drift, field removals, max_length increases, and required→optional flips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.schema_preamble import PREAMBLE_END, PREAMBLE_START, _PREAMBLE_PATTERN

# Regex to match a markdown table data row: | val | val | val |
_TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")


@dataclass
class PreambleProtectionResult:
    """Result of preamble protection validation."""

    valid: bool = True
    preamble_present: bool = True
    preamble_at_top: bool = True
    fields_removed: list[str] = field(default_factory=list)
    fields_added: list[str] = field(default_factory=list)
    max_length_weakened: list[dict] = field(default_factory=list)
    required_relaxed: list[dict] = field(default_factory=list)
    violation_reasons: list[str] = field(default_factory=list)


def _parse_output_table(preamble_text: str) -> list[dict[str, Any]]:
    """Parse '## Required Output' markdown table from preamble text.

    Returns list of dicts with keys: field, type, max_length.
    max_length is int or None (when cell contains dash).
    """
    fields: list[dict[str, Any]] = []
    in_section = False

    for line in preamble_text.splitlines():
        stripped = line.strip()

        if stripped.startswith("## Required Output"):
            in_section = True
            continue

        if in_section and (
            stripped.startswith("##") or stripped.startswith("Timeout:")
        ):
            break

        if not in_section:
            continue

        # Skip header and separator rows
        if stripped.startswith("|---") or (
            "Field" in stripped and "Max Length" in stripped
        ):
            continue

        match = _TABLE_ROW_RE.match(stripped)
        if match:
            field_name = match.group(1).strip()
            field_type = match.group(2).strip()
            max_len_str = match.group(3).strip()

            if max_len_str in ("\u2014", "-", "None", "\u2013"):
                max_length = None
            else:
                try:
                    max_length = int(max_len_str)
                except ValueError:
                    max_length = None

            fields.append(
                {
                    "field": field_name,
                    "type": field_type,
                    "max_length": max_length,
                }
            )

    return fields


def _parse_input_table(preamble_text: str) -> list[dict[str, Any]]:
    """Parse '## Expected Input' markdown table from preamble text.

    Returns list of dicts with keys: field, type, required.
    required is bool (parsed from 'yes'/'no').
    """
    fields: list[dict[str, Any]] = []
    in_section = False

    for line in preamble_text.splitlines():
        stripped = line.strip()

        if stripped.startswith("## Expected Input"):
            in_section = True
            continue

        if in_section and stripped.startswith("##"):
            break

        if not in_section:
            continue

        # Skip header and separator rows
        if stripped.startswith("|---") or (
            "Field" in stripped and "Required" in stripped
        ):
            continue

        match = _TABLE_ROW_RE.match(stripped)
        if match:
            field_name = match.group(1).strip()
            field_type = match.group(2).strip()
            required_str = match.group(3).strip().lower()

            fields.append(
                {
                    "field": field_name,
                    "type": field_type,
                    "required": required_str in ("yes", "true"),
                }
            )

    return fields


def validate_preamble_protection(
    original_template: str,
    mutated_template: str,
) -> PreambleProtectionResult:
    """Validate GEPA mutation hasn't weakened the schema preamble.

    Checks:
    1. Preamble markers present in mutated template
    2. Preamble at top (first non-whitespace content)
    3. All output fields preserved (no removals)
    4. max_length not increased (or changed from value to None)
    5. Required fields not changed to optional

    If original has no preamble, returns valid=True (nothing to protect).
    """
    result = PreambleProtectionResult()

    # Extract preamble from original
    orig_match = _PREAMBLE_PATTERN.search(original_template)
    if orig_match is None:
        # No preamble in original — nothing to protect
        return result

    original_preamble = orig_match.group(0)

    # Check 1: Preamble markers present in mutated
    has_start = PREAMBLE_START in mutated_template
    has_end = PREAMBLE_END in mutated_template

    if not has_start or not has_end:
        result.preamble_present = False
        result.valid = False
        result.violation_reasons.append("Preamble markers missing from candidate")
        return result

    # Check 2: Preamble at top of template
    if not mutated_template.lstrip().startswith(PREAMBLE_START):
        result.preamble_at_top = False
        result.valid = False
        result.violation_reasons.append("Preamble not at top of template")
        # Continue checking content even if position is wrong

    # Extract mutated preamble for content comparison
    mutated_match = _PREAMBLE_PATTERN.search(mutated_template)
    if mutated_match is None:
        result.preamble_present = False
        result.valid = False
        result.violation_reasons.append("Preamble markers missing from candidate")
        return result

    mutated_preamble = mutated_match.group(0)

    # Check 3: Output field preservation
    orig_output = _parse_output_table(original_preamble)
    mutated_output = _parse_output_table(mutated_preamble)

    orig_output_map = {f["field"]: f for f in orig_output}
    mutated_output_map = {f["field"]: f for f in mutated_output}

    for field_name in orig_output_map:
        if field_name not in mutated_output_map:
            result.fields_removed.append(field_name)
            result.violation_reasons.append(f"Output field '{field_name}' removed")

    for field_name in mutated_output_map:
        if field_name not in orig_output_map:
            result.fields_added.append(field_name)

    # Check 4: max_length not weakened
    for field_name, orig_field in orig_output_map.items():
        if field_name not in mutated_output_map:
            continue
        mutated_field = mutated_output_map[field_name]
        orig_ml = orig_field["max_length"]
        mutated_ml = mutated_field["max_length"]

        if orig_ml is not None:
            if mutated_ml is None:
                # Value → None is weakening
                result.max_length_weakened.append(
                    {
                        "field": field_name,
                        "original": orig_ml,
                        "mutated": None,
                    }
                )
                result.violation_reasons.append(
                    f"max_length for '{field_name}' weakened: {orig_ml} \u2192 None"
                )
            elif mutated_ml > orig_ml:
                # Increased is weakening
                result.max_length_weakened.append(
                    {
                        "field": field_name,
                        "original": orig_ml,
                        "mutated": mutated_ml,
                    }
                )
                result.violation_reasons.append(
                    f"max_length for '{field_name}' weakened: {orig_ml} \u2192 {mutated_ml}"
                )

    # Check 5: Required fields not relaxed
    orig_input = _parse_input_table(original_preamble)
    mutated_input = _parse_input_table(mutated_preamble)

    orig_input_map = {f["field"]: f for f in orig_input}
    mutated_input_map = {f["field"]: f for f in mutated_input}

    for field_name, orig_field in orig_input_map.items():
        if field_name not in mutated_input_map:
            continue
        if orig_field["required"] and not mutated_input_map[field_name]["required"]:
            result.required_relaxed.append(
                {
                    "field": field_name,
                    "original": True,
                    "mutated": False,
                }
            )
            result.violation_reasons.append(
                f"Field '{field_name}' changed from required to optional"
            )

    result.valid = len(result.violation_reasons) == 0
    return result
