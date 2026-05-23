"""Fallback prompts for BPV — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a brand personality strategist using the Aaker 5-Dimension "
    "model. Define brand personality, archetypes, core values, and "
    "voice matrix."
)

FALLBACK_PERSONALITY = (
    "Define brand personality using Aaker's 5 dimensions. Score each "
    "dimension 0-100 and identify the dominant archetype. Respond "
    "with valid JSON."
)

FALLBACK_VOICE = (
    "Create a brand voice matrix with voice attributes, tone guidelines, "
    "vocabulary preferences, and channel-specific adaptations. Respond "
    "with valid JSON."
)

FALLBACK_MAP = {
    "zorven-wf2-bpv-system": FALLBACK_SYSTEM,
    "zorven-wf2-bpv-personality": FALLBACK_PERSONALITY,
    "zorven-wf2-bpv-voice": FALLBACK_VOICE,
}
