"""Voice consistency scorer for BPV (brand-personality-agent-svc).

Checks aaker_profile, archetype, and values_hierarchy components.
Score = valid components / 3.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)


def _parse_output(outputs) -> dict | None:
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


@scorer(name="voice_consistency")
def voice_consistency(*, inputs, outputs, expectations=None):
    """Score voice consistency from BPV output.

    Checks:
    - aaker_profile: dict with 'dimensions' list of dicts having 'score' 0-100
    - archetype: dict with 'resonance_score' 0-1
    - values_hierarchy: dict with 'authenticity_score'

    Returns:
        Feedback with value 0.0-1.0 (valid components / 3).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="voice_consistency",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    valid_count = 0
    details = []

    # 1. aaker_profile
    aaker = data.get("aaker_profile")
    if isinstance(aaker, dict):
        dimensions = aaker.get("dimensions")
        if isinstance(dimensions, list) and len(dimensions) > 0:
            all_valid = True
            for dim in dimensions:
                if not isinstance(dim, dict):
                    all_valid = False
                    break
                score = dim.get("score")
                if not isinstance(score, (int, float)):
                    all_valid = False
                    break
                if not (0 <= float(score) <= 100):
                    all_valid = False
                    break
            if all_valid:
                valid_count += 1
                details.append(f"aaker_profile valid ({len(dimensions)} dimensions)")
            else:
                details.append("aaker_profile.dimensions contains invalid entries")
        else:
            details.append("aaker_profile.dimensions missing or empty")
    else:
        details.append("aaker_profile missing or not a dict")

    # 2. archetype
    archetype = data.get("archetype")
    if isinstance(archetype, dict):
        resonance = archetype.get("resonance_score")
        if isinstance(resonance, (int, float)) and 0.0 <= float(resonance) <= 1.0:
            valid_count += 1
            details.append(f"archetype valid (resonance_score={float(resonance):.2f})")
        else:
            details.append("archetype.resonance_score invalid or out of range")
    else:
        details.append("archetype missing or not a dict")

    # 3. values_hierarchy
    values = data.get("values_hierarchy")
    if isinstance(values, dict):
        authenticity = values.get("authenticity_score")
        if isinstance(authenticity, (int, float)):
            valid_count += 1
            details.append(
                f"values_hierarchy valid (authenticity_score={float(authenticity):.2f})"
            )
        else:
            details.append("values_hierarchy.authenticity_score invalid")
    else:
        details.append("values_hierarchy missing or not a dict")

    final_score = round(valid_count / 3.0, 4)

    return Feedback(
        name="voice_consistency",
        value=final_score,
        rationale=f"Score {final_score:.2f} ({valid_count}/3 components valid): "
        f"{'; '.join(details)}",
    )
