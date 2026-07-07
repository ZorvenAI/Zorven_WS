"""Fallback prompts for BSA — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a brand storytelling strategist. Craft origin stories, "
    "mission/vision statements, elevator pitches, and channel-specific "
    "narratives."
)

FALLBACK_NARRATIVE = (
    "Develop the brand narrative including mission statement, vision "
    "statement, and 30-second elevator pitch. Respond with valid JSON."
)

FALLBACK_ORIGIN = (
    "Craft an origin story that connects emotionally with the target "
    "audience. Respond with valid JSON."
)

FALLBACK_MAP = {
    "zorven-wf2-bsa-system": FALLBACK_SYSTEM,
    "zorven-wf2-bsa-narrative": FALLBACK_NARRATIVE,
    "zorven-wf2-bsa-origin": FALLBACK_ORIGIN,
}
