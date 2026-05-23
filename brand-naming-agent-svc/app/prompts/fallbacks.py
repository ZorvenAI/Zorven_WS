"""Fallback prompts for NTA — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a brand naming specialist. Generate name candidates with "
    "availability assessment and tagline synthesis. Consider linguistic "
    "analysis, cultural sensitivity, and domain availability."
)

FALLBACK_NAMING = (
    "Generate 5-7 brand name candidates with etymology, phonetic "
    "analysis, and preliminary availability check. Respond with "
    "valid JSON."
)

FALLBACK_TAGLINE = (
    "Create 5 tagline candidates with rationale, memorability score, "
    "and versatility assessment. Respond with valid JSON."
)

FALLBACK_MAP = {
    "zorven-wf2-nta-system": FALLBACK_SYSTEM,
    "zorven-wf2-nta-naming": FALLBACK_NAMING,
    "zorven-wf2-nta-tagline": FALLBACK_TAGLINE,
}
