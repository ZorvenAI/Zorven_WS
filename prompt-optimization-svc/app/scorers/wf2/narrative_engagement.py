"""Narrative engagement scorer for BSA (brand-story-agent-svc).

Checks origin_story, mission_vision, pitches, and channel_narratives.
Score = sections present / 4.
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


@scorer(name="narrative_engagement")
def narrative_engagement(*, inputs, outputs, expectations=None):
    """Score narrative engagement from BSA output.

    Checks presence of:
    - origin_story: dict
    - mission_vision: dict
    - pitches: dict or list
    - channel_narratives: dict

    Returns:
        Feedback with value 0.0-1.0 (sections present / 4).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="narrative_engagement",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    sections_present = 0
    details = []

    # 1. origin_story
    origin = data.get("origin_story")
    if isinstance(origin, dict):
        sections_present += 1
        details.append("origin_story present")
    else:
        details.append("origin_story missing or not a dict")

    # 2. mission_vision
    mission = data.get("mission_vision")
    if isinstance(mission, dict):
        sections_present += 1
        details.append("mission_vision present")
    else:
        details.append("mission_vision missing or not a dict")

    # 3. pitches (dict or list)
    pitches = data.get("pitches")
    if isinstance(pitches, (dict, list)):
        sections_present += 1
        details.append(f"pitches present ({type(pitches).__name__})")
    else:
        details.append("pitches missing or not a dict/list")

    # 4. channel_narratives
    narratives = data.get("channel_narratives")
    if isinstance(narratives, dict):
        sections_present += 1
        details.append("channel_narratives present")
    else:
        details.append("channel_narratives missing or not a dict")

    final_score = round(sections_present / 4.0, 4)

    return Feedback(
        name="narrative_engagement",
        value=final_score,
        rationale=f"Score {final_score:.2f} ({sections_present}/4 sections present): "
        f"{'; '.join(details)}",
    )
