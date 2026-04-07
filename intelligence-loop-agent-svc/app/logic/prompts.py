"""Prompt construction for ILA learning extraction."""

import json
from typing import Any

SYSTEM_PROMPT = (
    "You are the Intelligence Loop Agent (ILA) for an AI Brand Building "
    "platform. Your job is to mine strategic learnings from a single Meta "
    "Ads campaign's recent optimization history and brand context. "
    "You output ONLY valid JSON — no prose, no markdown fences. "
    "\n\n"
    "Each learning must fall into exactly one of five categories:\n"
    "  - audience    (who responds, who doesn't)\n"
    "  - messaging   (which copy/positioning lands)\n"
    "  - creative    (which formats/visuals work)\n"
    "  - funnel      (where users convert or drop off)\n"
    "  - competitive (positioning vs market)\n"
    "\n"
    "Each learning must specify a target workflow (WF1=research, "
    "WF2=strategy, WF3=campaign) and target agent code "
    "(APA, BPA, BAA, BPV, NTA, BSA, CAA, CGA, CIA, VOC, TCIA). "
    "Only emit a learning if the supporting evidence in the input is "
    "concrete (numbers, named entities, observed deltas). "
    "Confidence is an integer 0-100. Impact is LOW|MEDIUM|HIGH."
)

OUTPUT_SCHEMA = {
    "summary": "string — 2-3 sentence overall narrative",
    "learnings": [
        {
            "category": "audience|messaging|creative|funnel|competitive",
            "headline": "string — one-line takeaway",
            "detail": {
                "evidence": "string — supporting numbers/observations",
                "recommended_action": "string",
            },
            "confidence": "int 0-100",
            "impact": "LOW|MEDIUM|HIGH",
            "target_workflow": "WF1|WF2|WF3",
            "target_agent": "APA|BPA|BAA|BPV|NTA|BSA|CAA|CGA|CIA|VOC|TCIA",
        }
    ],
}


def build_user_prompt(context: dict[str, Any]) -> str:
    """Construct the user message from a campaign-context blob."""
    campaign = context.get("campaign", {}) or {}
    company = context.get("company", {}) or {}
    recommendations = context.get("recommendations", []) or []

    parts = [
        "Extract strategic learnings from the following campaign context.",
        "",
        "## Brand profile",
        json.dumps(company, indent=2, default=str),
        "",
        "## Campaign",
        json.dumps(campaign, indent=2, default=str),
        "",
        f"## Recent optimization recommendations ({len(recommendations)} total)",
        json.dumps(recommendations[:25], indent=2, default=str),
        "",
        "## Output format (return JSON matching this schema, no prose)",
        json.dumps(OUTPUT_SCHEMA, indent=2),
    ]
    return "\n".join(parts)
