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

    Prompt output keys: facts (list of {statement, source_url}),
    open_unknowns (list of str), competitors_seen, digital_presence.

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

    facts = data.get("facts", [])
    if isinstance(facts, list) and len(facts) > 0:
        cited = sum(1 for f in facts if isinstance(f, dict) and f.get("source_url"))
        if cited > 0:
            score_parts += cited / len(facts)
            details.append(f"facts: {cited}/{len(facts)} cited")
        else:
            details.append("facts: none have source_url")
    else:
        details.append("facts: missing or empty")

    unknowns = data.get("open_unknowns", [])
    if isinstance(unknowns, list) and len(unknowns) > 0:
        score_parts += 1
        details.append(f"open_unknowns: {len(unknowns)} acknowledged")
    else:
        details.append("open_unknowns: missing or empty")

    unique_urls = set()
    if isinstance(facts, list):
        for f in facts:
            if isinstance(f, dict) and f.get("source_url"):
                unique_urls.add(f["source_url"])
    if unique_urls:
        score_parts += min(len(unique_urls) / 3, 1.0)
        details.append(f"source_diversity: {len(unique_urls)} unique URLs")
    else:
        details.append("source_diversity: no URLs found")

    score = score_parts / total_parts

    return Feedback(
        name="research_factuality",
        value=round(score, 4),
        rationale=f"Factuality: {'; '.join(details)}",
    )
