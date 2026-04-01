"""SKL-CGA-10: Copy Compliance Checker.

Builds a prompt section for Claude call 3 that instructs Claude to
check all generated copy against Meta Advertising Standards, flagging
violations and warnings for prohibited content patterns.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Meta Advertising Standards violation categories
_META_AD_POLICIES: list[dict[str, str]] = [
    {
        "rule": "no_guaranteed_results",
        "description": (
            "Do not guarantee specific outcomes, results, or returns. "
            'Avoid: "guaranteed", "100% success", "you will earn".'
        ),
        "severity": "violation",
    },
    {
        "rule": "no_income_promises",
        "description": (
            "Do not promise specific income amounts or financial returns. "
            'Avoid: "make $X per day", "earn $X", "financial freedom guaranteed".'
        ),
        "severity": "violation",
    },
    {
        "rule": "no_miracle_cures",
        "description": (
            "Do not claim miracle cures, instant transformations, or "
            "medical results without proper disclaimers. "
            'Avoid: "cure", "miracle", "instant results", "clinically proven" '
            "without citations."
        ),
        "severity": "violation",
    },
    {
        "rule": "no_misleading_before_after",
        "description": (
            "Do not use misleading before/after imagery or claims that "
            "imply unrealistic transformations. Any transformation claims "
            "must be realistic and substantiated."
        ),
        "severity": "violation",
    },
    {
        "rule": "no_personal_attributes",
        "description": (
            "Do not assert or imply personal attributes about the viewer. "
            'Avoid: "Are you overweight?", "Do you have bad credit?", '
            '"Are you struggling with...?". Instead use general terms: '
            '"Looking for solutions to..." or "Many people find...".'
        ),
        "severity": "violation",
    },
    {
        "rule": "no_discriminatory_language",
        "description": (
            "Do not use language that discriminates based on race, "
            "ethnicity, gender, religion, age, disability, sexual "
            "orientation, or other protected characteristics."
        ),
        "severity": "violation",
    },
    {
        "rule": "no_profanity_or_grammar_errors",
        "description": (
            "Ad copy must be free of profanity, excessive capitalization "
            "(all caps for more than one word), and egregious grammar errors."
        ),
        "severity": "warning",
    },
    {
        "rule": "no_misleading_ctas",
        "description": (
            "CTA must accurately represent the landing page action. "
            '"Shop Now" must lead to a shop, "Download" must lead to a download.'
        ),
        "severity": "warning",
    },
    {
        "rule": "industry_health_wellness",
        "description": (
            "Health/wellness industry: No claims about treating, curing, "
            "or preventing diseases. No body shaming. Use empowering, "
            "positive framing."
        ),
        "severity": "violation",
    },
    {
        "rule": "industry_financial",
        "description": (
            "Financial services industry: Include required disclaimers. "
            "No guaranteed returns. Must comply with Special Ad Category "
            "requirements if applicable."
        ),
        "severity": "violation",
    },
    {
        "rule": "industry_alcohol",
        "description": (
            "Alcohol industry: Must comply with local laws. "
            "No targeting of minors. Include age restrictions."
        ),
        "severity": "violation",
    },
]


class CopyComplianceChecker:
    """Builds prompt section for Meta Advertising Standards compliance."""

    def build_prompt_section(self, creative_context: dict[str, Any]) -> str:
        """Build a prompt section for Claude call 3.

        Instructs Claude to check all generated copy against Meta
        Advertising Standards and flag violations/warnings.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        company = creative_context.get("company", {})
        industry = company.get("industry", "").lower()

        section = "## Meta Advertising Standards Compliance Check\n\n"
        section += (
            "Review ALL generated copy (hooks, primary text, CTAs) "
            "against Meta Advertising Standards. Each piece of copy "
            "must be checked for the following violations:\n\n"
        )

        # Core policies
        section += "### Core Policies\n\n"
        for policy in _META_AD_POLICIES:
            # Skip industry-specific rules if not relevant
            if policy["rule"].startswith("industry_"):
                industry_key = policy["rule"].replace("industry_", "")
                if industry_key not in industry and not self._industry_matches(
                    industry, industry_key
                ):
                    continue

            severity_label = (
                "VIOLATION" if policy["severity"] == "violation" else "WARNING"
            )
            section += (
                f"- **[{severity_label}] {policy['rule']}**: "
                f"{policy['description']}\n"
            )
        section += "\n"

        # Industry-specific context
        if industry:
            section += f"### Industry Context: {industry}\n"
            section += (
                f"This brand operates in the **{industry}** industry. "
                "Apply relevant industry-specific compliance rules. "
                "Flag any copy that may violate industry-specific "
                "advertising regulations.\n\n"
            )

        # Special Ad Category handling
        section += "### Special Ad Category Check\n"
        section += (
            "If the brand falls under Housing, Employment, or Credit "
            "categories, flag additional restrictions:\n"
            "- Limited targeting options (no age, gender, zip code targeting)\n"
            "- No discriminatory language or exclusionary terms\n"
            "- Additional disclaimer requirements\n\n"
        )

        # Output format
        section += "### Compliance Output Format\n\n"
        section += (
            "Output a `compliance_results` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "variant_id": "string",\n'
            '  "copy_type": "hook|primary_short|primary_medium|primary_long|cta",\n'
            '  "copy_text": "the actual text being checked",\n'
            '  "status": "pass|fail|warning",\n'
            '  "violations": [\n'
            "    {\n"
            '      "rule": "rule_name",\n'
            '      "severity": "violation|warning",\n'
            '      "description": "what specifically violated the rule",\n'
            '      "suggested_fix": "how to fix the violation"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "**Important**: Be thorough but not overly restrictive. "
            "Only flag genuine policy violations, not creative language "
            "choices. When in doubt, flag as 'warning' rather than 'fail'.\n"
        )

        return section

    def _industry_matches(self, industry: str, category: str) -> bool:
        """Check if industry matches a compliance category.

        Args:
            industry: Company industry string (lowercase).
            category: Compliance category key.

        Returns:
            True if industry matches the category.
        """
        mappings: dict[str, list[str]] = {
            "health_wellness": [
                "health",
                "wellness",
                "fitness",
                "nutrition",
                "supplement",
                "medical",
                "pharma",
                "beauty",
            ],
            "financial": [
                "finance",
                "banking",
                "insurance",
                "invest",
                "fintech",
                "credit",
                "lending",
            ],
            "alcohol": [
                "alcohol",
                "beverage",
                "brewery",
                "distillery",
                "wine",
                "spirits",
            ],
        }

        keywords = mappings.get(category, [])
        return any(kw in industry for kw in keywords)
