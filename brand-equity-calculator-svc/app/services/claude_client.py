"""Anthropic Claude API wrapper — ISO 20671:2019 brand equity evaluation.

Constructs the system + user prompts, calls Claude Opus 4.6, and
parses the structured JSON response into a validated dict.
"""

import json
import logging
import re
from typing import Any

from app.api.schemas import BrandEquityRequest
from app.core.config import settings

logger = logging.getLogger(__name__)

ISO_20671_SYSTEM_PROMPT = """\
You are an expert brand valuation analyst specialising in \
ISO 20671:2019 (Brand evaluation — Principles and fundamentals).

You evaluate brands across five weighted dimensions:

1. **Brand Governance** (Weight: 0.15)
   Strategy clarity, brand architecture, internal alignment, leadership \
commitment, brand guidelines adherence.

2. **Brand Engagement** (Weight: 0.25)
   Customer experience quality, employee engagement, stakeholder \
relations, community involvement, loyalty programs.

3. **Brand Perception** (Weight: 0.25)
   Market awareness, consideration, preference, advocacy, Net Promoter \
Score indicators, social sentiment.

4. **Brand Financial Performance** (Weight: 0.20)
   Revenue attribution to brand, price premium capability, market share, \
growth trajectory, brand-driven customer acquisition.

5. **Brand Protection** (Weight: 0.15)
   Legal protection (trademarks, IP), digital presence security, \
reputation management, crisis preparedness, domain authority.

For each dimension, score 0-100 based on PUBLICLY AVAILABLE information \
about the company and its industry.  Use your training data knowledge.

Additionally, identify 3-5 key competitors in the same industry and scope. \
For each competitor, provide an estimated brand equity score and list their \
main strengths and weaknesses relative to the company being evaluated.

IMPORTANT RULES:
- Be transparent about what you can and cannot assess.
- Flag all assumptions explicitly.
- Extrapolate from industry benchmarks for lesser-known companies.
- Return ONLY a JSON object — no markdown, no code fences, no explanation outside the JSON.

Return this exact JSON structure:
{
  "overall_score": <int 0-100>,
  "dimensions": [
    {
      "name": "Brand Governance",
      "score": <int 0-100>,
      "weight": 0.15,
      "rationale": "<2-3 sentence explanation>",
      "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
    },
    {
      "name": "Brand Engagement",
      "score": <int 0-100>,
      "weight": 0.25,
      "rationale": "<2-3 sentence explanation>",
      "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
    },
    {
      "name": "Brand Perception",
      "score": <int 0-100>,
      "weight": 0.25,
      "rationale": "<2-3 sentence explanation>",
      "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
    },
    {
      "name": "Brand Financial Performance",
      "score": <int 0-100>,
      "weight": 0.20,
      "rationale": "<2-3 sentence explanation>",
      "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
    },
    {
      "name": "Brand Protection",
      "score": <int 0-100>,
      "weight": 0.15,
      "rationale": "<2-3 sentence explanation>",
      "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
    }
  ],
  "competitors": [
    {
      "name": "<competitor company name>",
      "headquarters": "<city, state/country — e.g. Beaverton, Oregon, USA>",
      "estimated_score": <int 0-100>,
      "strengths": ["<strength1>", "<strength2>"],
      "weaknesses": ["<weakness1>", "<weakness2>"]
    }
  ],
  "formula_explanation": "<explain: Overall = sum(score_i * weight_i) with the actual numbers>",
  "derivation": "<step-by-step: how you arrived at each dimension score>",
  "limitations": ["<limitation1>", "<limitation2>", "<limitation3>", ...],
  "recommendations": ["<recommendation1>", "<recommendation2>", "<recommendation3>", ...]
}
"""


def _build_user_prompt(request: BrandEquityRequest) -> str:
    """Build the user prompt from form data."""
    return (
        "Evaluate the brand equity for the following company "
        "using ISO 20671:2019:\n\n"
        f"Company Name: {request.company_name}\n"
        f"Address: {request.address or 'Not provided'}\n"
        f"Website: {request.website or 'Not provided'}\n"
        f"Industry: {request.industry_type}\n"
        f"Business Size: {request.business_size}\n"
        f"Scope: {request.scope}\n\n"
        "Using your knowledge of this company and its industry, "
        "score each of the five ISO 20671 dimensions.  If the company "
        "is not widely known, use industry benchmarks for companies of "
        "similar size and scope, and clearly state this in your "
        "limitations.  Provide at least 5 specific, actionable "
        "recommendations to improve brand equity."
    )


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that Claude sometimes wraps JSON in."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class ClaudeClient:
    """Wrapper around the Anthropic async client for brand equity evaluation."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def evaluate_brand_equity(
        self, request: BrandEquityRequest
    ) -> dict[str, Any]:
        """Call Claude to evaluate brand equity and return parsed JSON."""
        logger.info(
            "Calling Claude (%s) for brand equity: %s",
            settings.CLAUDE_MODEL,
            request.company_name,
        )

        message = await self._client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=ISO_20671_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(request)}],
        )

        raw_text = next((b.text for b in message.content if b.type == "text"), None)
        if raw_text is None:
            raise ValueError("Claude returned no text content block")
        cleaned = _strip_code_fences(raw_text)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse Claude response as JSON: %s\nRaw: %s",
                exc,
                cleaned[:500],
            )
            raise ValueError(
                "AI returned an invalid response. Please try again."
            ) from exc

        logger.info(
            "Claude evaluation complete for %s: overall_score=%s",
            request.company_name,
            result.get("overall_score"),
        )
        return result
