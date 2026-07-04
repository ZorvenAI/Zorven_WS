"""Name quality scorer for NTA (brand-naming-agent-svc).

Checks name_candidates, shortlisted_names, and taglines components.
Score = checks passed / 3.
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


@scorer(name="name_quality")
def name_quality(*, inputs, outputs, expectations=None):
    """Score name quality from NTA output.

    Checks:
    - name_candidates: non-empty list of dicts with score fields
    - shortlisted_names: non-empty list
    - taglines: list with 'memorability_score'

    Returns:
        Feedback with value 0.0-1.0 (checks passed / 3).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="name_quality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    checks_passed = 0
    details = []

    # 1. name_candidates
    candidates = data.get("name_candidates")
    if isinstance(candidates, list) and len(candidates) > 0:
        has_scores = False
        for c in candidates:
            if not isinstance(c, dict):
                continue
            # Check for any score-like field
            score_fields = [k for k in c.keys() if "score" in k.lower()]
            if score_fields:
                has_scores = True
                break
        if has_scores:
            checks_passed += 1
            details.append(
                f"name_candidates valid ({len(candidates)} candidates with scores)"
            )
        else:
            details.append("name_candidates present but no score fields found")
    else:
        details.append("name_candidates missing or empty")

    # 2. shortlisted_names
    shortlisted = data.get("shortlisted_names")
    if isinstance(shortlisted, list) and len(shortlisted) > 0:
        checks_passed += 1
        details.append(f"shortlisted_names valid ({len(shortlisted)} names)")
    else:
        details.append("shortlisted_names missing or empty")

    # 3. taglines
    taglines = data.get("taglines")
    if isinstance(taglines, list) and len(taglines) > 0:
        has_memorability = False
        for t in taglines:
            if not isinstance(t, dict):
                continue
            mem_score = t.get("memorability_score")
            if isinstance(mem_score, (int, float)):
                has_memorability = True
                break
        if has_memorability:
            checks_passed += 1
            details.append("taglines valid (memorability_score present)")
        else:
            details.append("taglines present but no memorability_score found")
    else:
        details.append("taglines missing or empty")

    final_score = round(checks_passed / 3.0, 4)

    return Feedback(
        name="name_quality",
        value=final_score,
        rationale=f"Score {final_score:.2f} ({checks_passed}/3 checks passed): "
        f"{'; '.join(details)}",
    )
