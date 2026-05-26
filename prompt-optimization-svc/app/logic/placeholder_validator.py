"""Template placeholder validation (AC-2) and invariance guardrail (OPT-11).

Ensures prompt templates only contain {context.*} placeholders,
preventing PII from being baked into optimization snapshots.

Also validates placeholder invariance across GEPA mutations — rejecting
candidates that drop original placeholders and flagging new ones.

Handles both Python {var} and MLflow {{var}} placeholder syntax.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.registries.context_variables import VALID_PLACEHOLDER_NAMES

logger = logging.getLogger(__name__)

# Match {word.word} (single brace)
_SINGLE_BRACE_PATTERN = re.compile(r"(?<!\{)\{([\w.]+)\}(?!\})")

# Match {{word.word}} (MLflow double brace)
_DOUBLE_BRACE_PATTERN = re.compile(r"\{\{([\w.]+)\}\}")


def extract_placeholders(template: str) -> set[str]:
    """Extract all placeholder names from a template.

    Handles both Python {var} and MLflow {{var}} syntax.
    """
    single = set(_SINGLE_BRACE_PATTERN.findall(template))
    double = set(_DOUBLE_BRACE_PATTERN.findall(template))
    return single | double


def validate_template_placeholders(
    template: str,
    allowed_prefixes: tuple[str, ...] = ("context.",),
    registry: Optional[set[str]] = None,
) -> list[str]:
    """Validate that all placeholders use allowed prefixes.

    Args:
        template: Prompt template text (Python or MLflow syntax).
        allowed_prefixes: Tuple of allowed placeholder prefixes.
        registry: Optional set of valid placeholder names for strict check.
                  Use explicit None to skip registry validation.

    Returns:
        List of violation messages (empty = valid).
    """
    placeholders = extract_placeholders(template)
    violations: list[str] = []

    for ph in placeholders:
        # Check prefix
        if not any(ph.startswith(prefix) for prefix in allowed_prefixes):
            violations.append(
                f"Placeholder '{{{ph}}}' does not use allowed prefix "
                f"({', '.join(allowed_prefixes)})"
            )
        # Check registry if explicitly provided (including empty set)
        elif registry is not None and ph not in registry:
            violations.append(
                f"Placeholder '{{{ph}}}' not in context variable registry"
            )

    return violations


@dataclass
class PlaceholderInvarianceResult:
    """Result of placeholder invariance validation (OPT-11)."""

    valid: bool = True
    removed: set[str] = field(default_factory=set)
    added: set[str] = field(default_factory=set)
    needs_review: bool = False
    original_count: int = 0
    mutated_count: int = 0


def validate_placeholder_invariance(
    original: str,
    mutated: str,
) -> PlaceholderInvarianceResult:
    """Validate that a GEPA mutation preserves all original placeholders.

    Args:
        original: The original prompt template.
        mutated: The GEPA-mutated candidate template.

    Returns:
        PlaceholderInvarianceResult with:
        - valid=False if any placeholder was removed (AC-2)
        - needs_review=True if new placeholders were added (AC-3)
    """
    original_ph = extract_placeholders(original)
    mutated_ph = extract_placeholders(mutated)

    removed = original_ph - mutated_ph
    added = mutated_ph - original_ph

    if removed:
        logger.error(
            "OPT-11: GEPA mutation removed placeholders: %s",
            ", ".join(sorted(removed)),
        )

    if added:
        logger.warning(
            "OPT-11: GEPA mutation introduced new placeholders "
            "(flagged for review): %s",
            ", ".join(sorted(added)),
        )

    return PlaceholderInvarianceResult(
        valid=len(removed) == 0,
        removed=removed,
        added=added,
        needs_review=len(added) > 0,
        original_count=len(original_ph),
        mutated_count=len(mutated_ph),
    )
