"""Template placeholder validation (AC-2).

Ensures prompt templates only contain {context.*} placeholders,
preventing PII from being baked into optimization snapshots.
"""

import re
from typing import Optional

from app.registries.context_variables import VALID_PLACEHOLDER_NAMES

# Match {word.word} but not {{escaped}}
_PLACEHOLDER_PATTERN = re.compile(r"(?<!\{)\{([\w.]+)\}(?!\})")


def extract_placeholders(template: str) -> set[str]:
    """Extract all {placeholder} names from a template."""
    return set(_PLACEHOLDER_PATTERN.findall(template))


def validate_template_placeholders(
    template: str,
    allowed_prefixes: tuple[str, ...] = ("context.",),
    registry: Optional[set[str]] = None,
) -> list[str]:
    """Validate that all placeholders use allowed prefixes.

    Args:
        template: Prompt template text.
        allowed_prefixes: Tuple of allowed placeholder prefixes.
        registry: Optional set of valid placeholder names for strict check.

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
        # Check registry if provided
        elif registry and ph not in registry:
            violations.append(
                f"Placeholder '{{{ph}}}' not in context variable registry"
            )

    return violations
