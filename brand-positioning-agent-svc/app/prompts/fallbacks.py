"""Fallback prompts for BPA — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a brand positioning strategist. Develop differentiated "
    "positioning strategies using frameworks like classic positioning, "
    "blue ocean, JTBD, and challenger brand strategies."
)

FALLBACK_POSITIONING = (
    "Develop a brand positioning strategy with 3 positioning candidates "
    "including rationale, tagline, and value proposition. Respond with "
    "valid JSON."
)

FALLBACK_PERCEPTUAL = (
    "Create a perceptual positioning map against competitors. Select the "
    "two most differentiating dimensions, plot each brand, and identify "
    "white-space opportunities. Respond with valid JSON."
)

FALLBACK_MAP = {
    "zorven-wf2-bpa-system": FALLBACK_SYSTEM,
    "zorven-wf2-bpa-positioning": FALLBACK_POSITIONING,
    "zorven-wf2-bpa-perceptual": FALLBACK_PERCEPTUAL,
}
