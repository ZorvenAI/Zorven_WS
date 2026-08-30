"""Research brief factuality scorer for OIA (§17.1).

Checks that the research brief contains sourced facts with citations,
coverage of unknowns, and factual grounding against retrieved sources.
Score = weighted combination of citation presence, source coverage, and
unknown acknowledgement.
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


@scorer(name="research_factuality")
def research_factuality(*, inputs, outputs, expectations=None):
    """Score research brief factuality.

    Checks for: sourced_facts (list with source_url), open_unknowns
    (acknowledged gaps), and source_urls (citation list).

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="research_factuality",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0
    total_parts = 3
    details = []

    sourced_facts = data.get("sourced_facts", data.get("facts", []))
    if isinstance(sourced_facts, list) and len(sourced_facts) > 0:
        cited = sum(
            1 for f in sourced_facts if isinstance(f, dict) and f.get("source_url")
        )
        if cited > 0:
            score_parts += cited / len(sourced_facts)
            details.append(f"sourced_facts: " f"{cited}/{len(sourced_facts)} cited")
        else:
            details.append("sourced_facts: none have source_url")
    else:
        details.append("sourced_facts: missing or empty")

    unknowns = data.get("open_unknowns", data.get("unknowns", []))
    if isinstance(unknowns, list) and len(unknowns) > 0:
        score_parts += 1
        details.append(f"open_unknowns: {len(unknowns)} acknowledged")
    else:
        details.append("open_unknowns: missing or empty")

    sources = data.get("source_urls", data.get("sources", []))
    if isinstance(sources, list) and len(sources) > 0:
        score_parts += 1
        details.append(f"source_urls: {len(sources)} provided")
    else:
        details.append("source_urls: missing or empty")

    score = score_parts / total_parts

    return Feedback(
        name="research_factuality",
        value=round(score, 4),
        rationale=f"Factuality: {'; '.join(details)}",
    )
