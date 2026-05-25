"""Brand voice scorer (§5.1, AC-3).

Uses an Anthropic Claude LLM judge with a 0-5 rubric mapped to 0.0-1.0.
The rubric evaluates brand voice consistency in model output.
"""

import json
import logging

import anthropic

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

from app.core.config import settings

logger = logging.getLogger(__name__)

BRAND_VOICE_RUBRIC = """You are a brand voice evaluator. Rate how well the following text matches the specified brand voice on a 0-5 scale.

## Brand Voice Description
{brand_voice}

## Text to Evaluate
{text}

## Rubric
- 0: Completely off-brand — wrong tone, style, or register
- 1: Mostly off-brand with occasional alignment
- 2: Mixed — some brand elements present but inconsistent
- 3: Adequate brand voice — meets minimum standard
- 4: Strong brand voice alignment throughout
- 5: Perfect brand voice — exemplary and consistent

## Instructions
Respond with ONLY a JSON object in this exact format:
{{"score": <integer 0-5>, "justification": "<one sentence explanation>"}}"""

DEFAULT_BRAND_VOICE = (
    "Professional, clear, and authoritative. "
    "Uses precise language, avoids jargon, and maintains a helpful, "
    "confident tone appropriate for business communication."
)


@scorer(name="brand_voice")
def brand_voice(*, inputs, outputs, expectations=None):
    """Score brand voice consistency using an LLM judge.

    Args:
        inputs: Model input (unused).
        outputs: Model output text to evaluate.
        expectations: Dict with optional "brand_voice" key describing
            the target voice. Falls back to generic professional voice.

    Returns:
        Feedback with value 0.0–1.0 (mapped from 0–5 rubric).
    """
    if outputs is None or str(outputs).strip() == "":
        return Feedback(
            name="brand_voice",
            value=0.0,
            rationale="Empty output — cannot evaluate brand voice.",
        )

    if not settings.ANTHROPIC_API_KEY:
        return Feedback(
            name="brand_voice",
            value=0.0,
            rationale="Anthropic API key not configured — cannot evaluate brand voice.",
        )

    voice_description = DEFAULT_BRAND_VOICE
    if expectations and isinstance(expectations, dict):
        voice_description = expectations.get("brand_voice", DEFAULT_BRAND_VOICE)

    prompt = BRAND_VOICE_RUBRIC.format(
        brand_voice=voice_description,
        text=str(outputs),
    )

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    # Parse the JSON response from the LLM judge
    try:
        parsed = json.loads(response_text)
        raw_score = int(parsed.get("score", 0))
        raw_score = max(0, min(5, raw_score))
        justification = parsed.get("justification", response_text)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(
            "Could not parse brand voice JSON from LLM response: %s",
            response_text,
        )
        raw_score = 0
        justification = f"Parse error — raw response: {response_text}"

    normalized_score = round(raw_score / 5.0, 2)

    return Feedback(
        name="brand_voice",
        value=normalized_score,
        rationale=f"Brand voice score: {raw_score}/5. {justification}",
    )
