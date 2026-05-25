"""Brand voice match scorer for CGA (§5.2.1, AC-4).

Uses an Anthropic Claude LLM judge to evaluate brand voice consistency
across CGA ad copy (hooks + primary text). Scored 0-5, mapped to 0.0-1.0.
"""

import json
import logging

import anthropic

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

from app.core.config import settings

logger = logging.getLogger(__name__)

BRAND_VOICE_RUBRIC = """You are a brand voice evaluator for advertising copy. Rate how well the following ad creative text matches the specified brand voice on a 0-5 scale.

## Brand Voice Description
{brand_voice}

## Ad Creative Text
{text}

## Rubric
- 0: Completely off-brand — wrong tone, style, or register for this brand
- 1: Mostly off-brand with occasional alignment
- 2: Mixed — some brand elements present but inconsistent across copy
- 3: Adequate brand voice — meets minimum standard for ad copy
- 4: Strong brand voice alignment throughout all copy variants
- 5: Perfect brand voice — exemplary, consistent, and compelling

## Instructions
Respond with ONLY a JSON object in this exact format:
{{"score": <integer 0-5>, "justification": "<one sentence explanation>"}}"""

DEFAULT_BRAND_VOICE = (
    "Professional, clear, and action-oriented. "
    "Uses compelling language appropriate for Meta Ads with strong CTAs."
)


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


@scorer(name="brand_voice_match")
def brand_voice_match(*, inputs, outputs, expectations=None):
    """Score brand voice consistency across CGA ad copy.

    Concatenates hooks and copy variants into a single sample
    and evaluates via LLM judge.

    Args:
        inputs: Model input (unused).
        outputs: CGA response JSON with hooks and copy_variants.
        expectations: Dict with optional "brand_voice" key.

    Returns:
        Feedback with value 0.0–1.0 (mapped from 0–5 rubric).
    """
    data = _parse_cga_output(outputs)
    if data is None:
        return Feedback(
            name="brand_voice_match",
            value=0.0,
            rationale="Invalid or missing CGA output.",
        )

    # Collect ad copy samples before checking API key
    samples = []
    for hook in data.get("hooks", [])[:5]:
        text = hook.get("hook_text", "").strip()
        if text:
            samples.append(f"Hook: {text}")
    for cv in data.get("copy_variants", [])[:5]:
        text = cv.get("copy_text", "").strip()
        if text:
            label = cv.get("length_label", "")
            samples.append(f"Copy ({label}): {text}")

    if not samples:
        return Feedback(
            name="brand_voice_match",
            value=0.0,
            rationale="No ad copy found in CGA output to evaluate.",
        )

    if not settings.ANTHROPIC_API_KEY:
        return Feedback(
            name="brand_voice_match",
            value=0.0,
            rationale="Anthropic API key not configured — cannot evaluate brand voice.",
        )

    voice_description = DEFAULT_BRAND_VOICE
    if expectations and isinstance(expectations, dict):
        voice_description = expectations.get("brand_voice", DEFAULT_BRAND_VOICE)

    combined_text = "\n".join(samples)
    prompt = BRAND_VOICE_RUBRIC.format(
        brand_voice=voice_description,
        text=combined_text,
    )

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    try:
        parsed = json.loads(response_text)
        raw_score = int(parsed.get("score", 0))
        raw_score = max(0, min(5, raw_score))
        justification = parsed.get("justification", response_text)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(
            "Could not parse brand voice match JSON from LLM response: %s",
            response_text,
        )
        raw_score = 0
        justification = f"Parse error — raw response: {response_text}"

    normalized_score = round(raw_score / 5.0, 2)

    return Feedback(
        name="brand_voice_match",
        value=normalized_score,
        rationale=f"Brand voice score: {raw_score}/5. {justification}",
    )
