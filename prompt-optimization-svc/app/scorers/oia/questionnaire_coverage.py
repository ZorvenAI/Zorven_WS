"""Questionnaire coverage scorer for OIA (§17.1).

Checks that the generated questionnaire covers required workflows,
has precise questions, and adheres to count/depth constraints.
Score = weighted combination of workflow coverage, question precision,
and count adherence.
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


@scorer(name="questionnaire_coverage")
def questionnaire_coverage(*, inputs, outputs, expectations=None):
    """Score questionnaire workflow coverage and question quality.

    Checks for: questions (list with workflow_id), workflow coverage
    completeness, and adherence to question count constraints.

    Returns:
        Feedback with value 0.0-1.0.
    """
    data = _parse_output(outputs)
    if data is None:
        return Feedback(
            name="questionnaire_coverage",
            value=0.0,
            rationale="Invalid or missing output.",
        )

    score_parts = 0.0
    total_parts = 3
    details = []

    questions = data.get("questions", [])
    if isinstance(questions, list) and len(questions) > 0:
        score_parts += 1
        details.append(f"questions: {len(questions)} generated")

        workflows_covered = set()
        for q in questions:
            if isinstance(q, dict):
                wf = q.get("workflow_id") or q.get("workflow")
                if wf:
                    workflows_covered.add(str(wf))
        if workflows_covered:
            score_parts += min(len(workflows_covered) / 3, 1.0)
            details.append("workflow_coverage: " f"{len(workflows_covered)} workflows")
        else:
            details.append("workflow_coverage: no workflow_id on questions")

        well_formed = sum(
            1
            for q in questions
            if isinstance(q, dict) and q.get("text") and q.get("rationale")
        )
        if well_formed > 0:
            score_parts += well_formed / len(questions)
            details.append(
                f"question_quality: {well_formed}/{len(questions)} well-formed"
            )
        else:
            details.append("question_quality: missing text or rationale")
    else:
        details.append("questions: missing or empty")

    score = score_parts / total_parts

    return Feedback(
        name="questionnaire_coverage",
        value=round(score, 4),
        rationale=f"Coverage: {'; '.join(details)}",
    )
