"""Persona quality scorer for APA (WF1).

Checks APA output for personas (list of dicts with demographics and
psychographics) and journey_maps (non-empty list).
Score = 50% complete personas ratio + 50% journey map presence.
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


@scorer(name="persona_quality")
def persona_quality(*, inputs, outputs, expectations=None):
    """Score APA output quality.

    50% weight on complete persona ratio (each persona must have a
    demographics dict and psychographics), 50% weight on journey_maps
    presence.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="persona_quality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    details = []

    # Check personas completeness (50% weight)
    personas = data.get("personas")
    persona_score = 0.0
    if isinstance(personas, list) and len(personas) > 0:
        complete = 0
        for p in personas:
            if not isinstance(p, dict):
                continue
            has_demographics = isinstance(p.get("demographics"), dict)
            has_psychographics = p.get("psychographics") is not None
            if has_demographics and has_psychographics:
                complete += 1
        persona_score = complete / len(personas)
        details.append(f"personas: {complete}/{len(personas)} complete")
    else:
        details.append("personas: missing or empty")

    # Check journey_maps presence (50% weight)
    journey_maps = data.get("journey_maps")
    journey_score = 0.0
    if isinstance(journey_maps, list) and len(journey_maps) > 0:
        journey_score = 1.0
        details.append(f"journey_maps: {len(journey_maps)} items")
    else:
        details.append("journey_maps: missing or empty")

    score = (persona_score * 0.5) + (journey_score * 0.5)

    return Feedback(
        name="persona_quality",
        value=round(score, 4),
        rationale=f"Persona ratio={persona_score:.2f}, journey_maps={'present' if journey_score else 'absent'}. {'; '.join(details)}",
    )
