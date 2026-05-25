"""Trend relevance scorer for TCIA (WF1).

Checks TCIA output for trend_report (dict with trend_scorecard list of dicts
having relevance_score 0-100) and opportunity_alerts (non-empty list).
Score = valid scored trends / total + alerts bonus.
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


@scorer(name="trend_relevance")
def trend_relevance(*, inputs, outputs, expectations=None):
    """Score TCIA output relevance.

    Primary component (80%): ratio of trends with valid relevance_score
    (0-100) in trend_report.trend_scorecard.
    Bonus component (20%): presence of non-empty opportunity_alerts.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="trend_relevance",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    details = []

    # Check trend_report.trend_scorecard (80% weight)
    trend_score = 0.0
    trend_report = data.get("trend_report")
    if isinstance(trend_report, dict):
        scorecard = trend_report.get("trend_scorecard")
        if isinstance(scorecard, list) and len(scorecard) > 0:
            valid_count = 0
            for entry in scorecard:
                if not isinstance(entry, dict):
                    continue
                rel = entry.get("relevance_score")
                if isinstance(rel, (int, float)) and 0 <= rel <= 100:
                    valid_count += 1
            trend_score = valid_count / len(scorecard)
            details.append(
                f"trend_scorecard: {valid_count}/{len(scorecard)} valid scores"
            )
        else:
            details.append("trend_scorecard: missing or empty")
    else:
        details.append("trend_report: missing or not a dict")

    # Check opportunity_alerts (20% weight)
    alerts_score = 0.0
    opportunity_alerts = data.get("opportunity_alerts")
    if isinstance(opportunity_alerts, list) and len(opportunity_alerts) > 0:
        alerts_score = 1.0
        details.append(f"opportunity_alerts: {len(opportunity_alerts)} items")
    else:
        details.append("opportunity_alerts: missing or empty")

    score = (trend_score * 0.8) + (alerts_score * 0.2)

    return Feedback(
        name="trend_relevance",
        value=round(score, 4),
        rationale=f"Trend validity={trend_score:.2f}, alerts={'present' if alerts_score else 'absent'}. {'; '.join(details)}",
    )
