"""Market completeness scorer for MRA (WF1).

Checks MRA output for market_sizing (TAM/SAM/SOM), competitive_landscape,
industry_trends, and findings. Score = present fields / 4.
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


@scorer(name="market_completeness")
def market_completeness(*, inputs, outputs, expectations=None):
    """Score MRA output completeness.

    Checks for four key fields: market_sizing (dict with TAM/SAM/SOM),
    competitive_landscape (non-empty list), industry_trends (non-empty list),
    and findings (non-empty list).

    Returns:
        Feedback with value 0.0-1.0 (present fields / 4).
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="market_completeness",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    present = 0
    details = []

    # Check market_sizing with TAM/SAM/SOM
    market_sizing = data.get("market_sizing")
    if isinstance(market_sizing, dict):
        tam_sam_som = all(
            market_sizing.get(k) is not None for k in ("TAM", "SAM", "SOM")
        )
        if tam_sam_som:
            present += 1
            details.append("market_sizing: present with TAM/SAM/SOM")
        else:
            details.append("market_sizing: missing TAM, SAM, or SOM keys")
    else:
        details.append("market_sizing: missing or not a dict")

    # Check competitive_landscape
    competitive_landscape = data.get("competitive_landscape")
    if isinstance(competitive_landscape, list) and len(competitive_landscape) > 0:
        present += 1
        details.append(f"competitive_landscape: {len(competitive_landscape)} items")
    else:
        details.append("competitive_landscape: missing or empty")

    # Check industry_trends
    industry_trends = data.get("industry_trends")
    if isinstance(industry_trends, list) and len(industry_trends) > 0:
        present += 1
        details.append(f"industry_trends: {len(industry_trends)} items")
    else:
        details.append("industry_trends: missing or empty")

    # Check findings
    findings = data.get("findings")
    if isinstance(findings, list) and len(findings) > 0:
        present += 1
        details.append(f"findings: {len(findings)} items")
    else:
        details.append("findings: missing or empty")

    score = present / 4.0

    return Feedback(
        name="market_completeness",
        value=score,
        rationale=f"{present}/4 fields present. {'; '.join(details)}",
    )
