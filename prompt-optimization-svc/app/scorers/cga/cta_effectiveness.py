"""CTA effectiveness scorer for CGA (§5.2.1, AC-5).

Rule-based scoring using action verb detection, urgency keywords,
and funnel-stage alignment for Meta Ads CTAs.
"""

import json
import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

ACTION_VERBS = {
    "get",
    "shop",
    "learn",
    "sign",
    "book",
    "download",
    "start",
    "try",
    "buy",
    "claim",
    "discover",
    "explore",
    "join",
    "save",
    "subscribe",
    "watch",
    "order",
    "apply",
    "request",
    "contact",
}

URGENCY_KEYWORDS = {
    "now",
    "today",
    "limited",
    "last chance",
    "don't miss",
    "hurry",
    "ends soon",
    "exclusive",
    "only",
    "instant",
    "free",
    "act fast",
}

# Valid CTA buttons per funnel stage
FUNNEL_CTA_MAP: dict[str, set[str]] = {
    "tofu": {"LEARN_MORE", "WATCH_MORE", "SEE_MORE"},
    "mofu": {"GET_OFFER", "DOWNLOAD", "GET_QUOTE", "LEARN_MORE", "SIGN_UP"},
    "bofu": {"SHOP_NOW", "SIGN_UP", "BOOK_NOW", "BUY_NOW", "ORDER_NOW", "GET_OFFER"},
    "retention": {"SHOP_NOW", "GET_OFFER", "BOOK_NOW", "ORDER_NOW"},
}

# Weights for composite score
W_ACTION_VERB = 0.30
W_URGENCY = 0.20
W_FUNNEL_ALIGNMENT = 0.30
W_CLARITY = 0.20


def _has_action_verb(text: str) -> bool:
    """Check if text starts with a recognized action verb."""
    first_word = text.strip().split()[0].lower() if text.strip() else ""
    return first_word in ACTION_VERBS


def _has_urgency(text: str) -> bool:
    """Check if text contains urgency keywords."""
    lower = text.lower()
    return any(kw in lower for kw in URGENCY_KEYWORDS)


def _funnel_aligned(cta_button: str, funnel_stage: str) -> bool:
    """Check if CTA button matches the funnel stage."""
    valid = FUNNEL_CTA_MAP.get(funnel_stage.lower(), set())
    return cta_button.upper() in valid


def _parse_cga_output(outputs) -> dict | None:
    """Parse CGA output from JSON string or dict."""
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


@scorer(name="cta_effectiveness")
def cta_effectiveness(*, inputs, outputs, expectations=None):
    """Score CTA effectiveness using rule-based analysis.

    Evaluates action verb usage, urgency keywords, funnel-stage
    alignment, and clarity scores for each CTA variant.

    Score = 30% action verb + 20% urgency + 30% funnel alignment + 20% clarity.

    Args:
        inputs: Model input (unused).
        outputs: CGA response JSON with ctas array.
        expectations: Optional (unused).

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_cga_output(outputs)
    if data is None:
        return Feedback(
            name="cta_effectiveness",
            value=0.0,
            rationale="Invalid or missing CGA output.",
        )

    ctas = data.get("ctas", [])
    if not ctas:
        return Feedback(
            name="cta_effectiveness",
            value=0.0,
            rationale="No CTAs found in CGA output.",
        )

    total_action = 0.0
    total_urgency = 0.0
    total_alignment = 0.0
    total_clarity = 0.0
    details = []

    for cta in ctas:
        text = cta.get("cta_text", "")
        button = cta.get("cta_button", "")
        funnel = cta.get("funnel_stage", "")
        clarity = cta.get("clarity_score", 0) / 100.0
        urgency_score = cta.get("urgency_score", 0) / 100.0

        has_verb = _has_action_verb(text)
        has_urg = _has_urgency(text)
        aligned = _funnel_aligned(button, funnel)

        action_score = 1.0 if has_verb else 0.0
        urgency_val = max(urgency_score, 1.0 if has_urg else 0.0)
        alignment_score = 1.0 if aligned else 0.0

        total_action += action_score
        total_urgency += urgency_val
        total_alignment += alignment_score
        total_clarity += clarity

        details.append(
            f"{button}({funnel}): verb={has_verb}, urgency={has_urg}, aligned={aligned}"
        )

    n = len(ctas)
    composite = (
        W_ACTION_VERB * (total_action / n)
        + W_URGENCY * (total_urgency / n)
        + W_FUNNEL_ALIGNMENT * (total_alignment / n)
        + W_CLARITY * (total_clarity / n)
    )
    score = round(min(1.0, max(0.0, composite)), 4)

    rationale = (
        f"{n} CTAs evaluated. "
        f"Action verbs: {int(total_action)}/{n}, "
        f"Funnel aligned: {int(total_alignment)}/{n}. " + "; ".join(details[:3])
    )
    if len(details) > 3:
        rationale += f" (+{len(details) - 3} more)"

    return Feedback(
        name="cta_effectiveness",
        value=score,
        rationale=rationale,
    )
