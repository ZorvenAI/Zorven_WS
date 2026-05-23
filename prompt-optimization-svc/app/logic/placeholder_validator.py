"""Template placeholder validation (AC-2).

Ensures prompt templates only contain {context.*} placeholders,
preventing PII from being baked into optimization snapshots.

Handles both Python {var} and MLflow {{var}} placeholder syntax.
"""

import re
from typing import Optional

from app.registries.context_variables import VALID_PLACEHOLDER_NAMES

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
