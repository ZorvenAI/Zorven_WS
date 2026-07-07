"""Architecture coherence scorer for BAA (brand-architecture-agent-svc).

Checks recommendation, hierarchy, and naming_hierarchy components.
Score = valid components present / 3.
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


@scorer(name="architecture_coherence")
def architecture_coherence(*, inputs, outputs, expectations=None):
    """Score architecture coherence from BAA output.

    Checks:
    - recommendation: dict with 'recommended_model' and 'model_scores' list
    - hierarchy: dict with 'root' and 'total_depth'
    - naming_hierarchy: dict with 'consistency_score' 0-1

    Returns:
        Feedback with value 0.0-1.0 (valid components / 3).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="architecture_coherence",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    valid_count = 0
    details = []

    # 1. recommendation
    rec = data.get("recommendation")
    if isinstance(rec, dict):
        has_model = (
            isinstance(rec.get("recommended_model"), str)
            and rec["recommended_model"].strip()
        )
        model_scores = rec.get("model_scores")
        has_scores = isinstance(model_scores, list) and len(model_scores) > 0
        if has_model and has_scores:
            valid_count += 1
            details.append("recommendation valid (recommended_model + model_scores)")
        else:
            missing = []
            if not has_model:
                missing.append("recommended_model")
            if not has_scores:
                missing.append("model_scores")
            details.append(f"recommendation incomplete: missing {', '.join(missing)}")
    else:
        details.append("recommendation missing or not a dict")

    # 2. hierarchy
    hier = data.get("hierarchy")
    if isinstance(hier, dict):
        has_root = hier.get("root") is not None
        total_depth = hier.get("total_depth")
        has_depth = isinstance(total_depth, (int, float))
        if has_root and has_depth:
            valid_count += 1
            details.append("hierarchy valid (root + total_depth)")
        else:
            missing = []
            if not has_root:
                missing.append("root")
            if not has_depth:
                missing.append("total_depth")
            details.append(f"hierarchy incomplete: missing {', '.join(missing)}")
    else:
        details.append("hierarchy missing or not a dict")

    # 3. naming_hierarchy
    naming = data.get("naming_hierarchy")
    if isinstance(naming, dict):
        consistency = naming.get("consistency_score")
        if isinstance(consistency, (int, float)) and float(consistency) >= 0:
            # Normalize 0-100 to 0-1 (also accepts 0-1 directly)
            val = float(consistency)
            normalized = val / 100.0 if val > 1.0 else val
            normalized = min(normalized, 1.0)
            valid_count += 1
            details.append(
                f"naming_hierarchy valid (consistency_score={normalized:.2f})"
            )
        else:
            details.append("naming_hierarchy.consistency_score invalid or out of range")
    else:
        details.append("naming_hierarchy missing or not a dict")

    final_score = round(valid_count / 3.0, 4)

    return Feedback(
        name="architecture_coherence",
        value=final_score,
        rationale=f"Score {final_score:.2f} ({valid_count}/3 components valid): "
        f"{'; '.join(details)}",
    )
