"""Synthetic context generator for golden evaluation datasets (§7.6.4).

Uses Claude Sonnet 4 to fabricate realistic brand profiles for an
(industry, maturity, objective) tuple. Never references real tenants.
"""

import json
import logging
from typing import Any

import anthropic

from app.datasets.golden_seed import INDUSTRIES, GoldenExample

VALID_MATURITIES = {"new", "emerging", "established"}

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a synthetic brand profile generator for AI evaluation datasets. "
    "Generate FICTIONAL brand profiles that are realistic but never reference "
    "real companies, real people, or real tenant data. All brand names must be "
    "completely invented."
)

GENERATION_PROMPT = """Generate a synthetic brand profile for the following parameters:

Industry: {industry}
Brand Maturity: {brand_maturity}
Business Objective: {objective}

Respond with ONLY a JSON object containing these fields:
{{
    "brand_name": "<fictional brand name - must be invented, never a real company>",
    "product_description": "<1-2 sentence description of what the company does>",
    "target_audience": "<description of the primary target audience>",
    "brand_voice": "<brand tone and communication style description>",
    "budget_range": "<realistic quarterly marketing budget range, e.g. $10K-50K/quarter>",
    "audience_complexity": "<simple|moderate|complex>",
    "voice_tone": "<1-2 word tone label, e.g. professional, playful, authoritative>"
}}"""

REQUIRED_FIELDS = (
    "brand_name",
    "product_description",
    "target_audience",
    "brand_voice",
    "budget_range",
    "audience_complexity",
    "voice_tone",
)


class SyntheticContextGenerator:
    """Generates synthetic brand profiles using Claude Sonnet 4.

    Produces fictional brand contexts for GEPA evaluation datasets,
    ensuring no real tenant data is referenced.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "Anthropic API key is required for synthetic context generation."
            )
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        industry: str,
        brand_maturity: str,
        objective: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Generate a single synthetic brand profile.

        Args:
            industry: Industry vertical (e.g., "SaaS/Technology").
            brand_maturity: Brand stage ("new", "emerging", "established").
            objective: Business objective (e.g., "Drive trial signups").

        Returns:
            Tuple of (context dict with context_ keys, raw profile dict).

        Raises:
            ValueError: If industry or brand_maturity is not in the canonical set.
        """
        if industry not in INDUSTRIES:
            raise ValueError(f"Unknown industry '{industry}'. Valid: {INDUSTRIES}")
        if brand_maturity not in VALID_MATURITIES:
            raise ValueError(
                f"Unknown brand_maturity '{brand_maturity}'. "
                f"Valid: {sorted(VALID_MATURITIES)}"
            )
        prompt = GENERATION_PROMPT.format(
            industry=industry,
            brand_maturity=brand_maturity,
            objective=objective,
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = next(
            b.text for b in response.content if b.type == "text"
        ).strip()

        try:
            profile = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse synthetic profile JSON: %s", response_text)
            raise ValueError(f"Claude returned invalid JSON: {response_text[:200]}")

        # Validate required fields
        for field in REQUIRED_FIELDS:
            if field not in profile or not profile[field]:
                raise ValueError(f"Generated profile missing required field: {field}")

        # Convert to context_ prefixed keys for GEPA train_data
        context = {
            "context_brand_name": profile["brand_name"],
            "context_industry": industry,
            "context_target_audience": profile["target_audience"],
            "context_brand_voice": profile["brand_voice"],
            "context_product_description": profile["product_description"],
        }

        return context, profile

    def generate_example(
        self,
        industry: str,
        brand_maturity: str,
        objective: str,
        prompt_name: str,
        agent_code: str,
    ) -> GoldenExample:
        """Generate a single GoldenExample with synthetic context.

        Args:
            industry: Industry vertical.
            brand_maturity: Brand stage.
            objective: Business objective.
            prompt_name: Target prompt name (e.g., "zorven-wf1-mra-system").
            agent_code: Agent code (e.g., "mra").

        Returns:
            GoldenExample with source="synthetic".
        """
        context, profile = self.generate(industry, brand_maturity, objective)

        return GoldenExample(
            prompt_name=prompt_name,
            agent_code=agent_code,
            input_context=context,
            expected_output=(
                f"Synthetic evaluation context for {profile['brand_name']} "
                f"({industry}, {brand_maturity}) targeting {objective}."
            ),
            source="synthetic",
            metadata_extra={
                "industry": industry,
                "brand_maturity": brand_maturity,
                "objective": objective,
                "voice_tone": profile.get("voice_tone", ""),
                "budget_range": profile.get("budget_range", ""),
                "audience_complexity": profile.get("audience_complexity", ""),
            },
        )

    def generate_batch(
        self,
        tuples: list[tuple[str, str, str]],
        prompt_name: str = "zorven-wf1-mra-system",
        agent_code: str = "mra",
    ) -> tuple[list[GoldenExample], list[str]]:
        """Generate multiple GoldenExamples from (industry, maturity, objective) tuples.

        Args:
            tuples: List of (industry, brand_maturity, objective) tuples.
            prompt_name: Default prompt name for generated examples.
            agent_code: Default agent code for generated examples.

        Returns:
            Tuple of (examples list, errors list). Errors list contains
            string descriptions of any failures.
        """
        examples = []
        errors = []
        for industry, maturity, objective in tuples:
            try:
                example = self.generate_example(
                    industry=industry,
                    brand_maturity=maturity,
                    objective=objective,
                    prompt_name=prompt_name,
                    agent_code=agent_code,
                )
                examples.append(example)
            except Exception as exc:
                error_msg = f"({industry}, {maturity}, {objective}): {exc}"
                errors.append(error_msg)
                logger.error("Failed to generate synthetic context: %s", error_msg)
        return examples, errors
