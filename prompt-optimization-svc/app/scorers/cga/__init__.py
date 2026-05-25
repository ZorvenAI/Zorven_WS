"""CGA creative generation scorers (§5.2.1)."""

from app.scorers.cga.brand_voice_match import brand_voice_match
from app.scorers.cga.character_limits import character_limits
from app.scorers.cga.creative_compliance import creative_compliance
from app.scorers.cga.cta_effectiveness import cta_effectiveness
from app.scorers.cga.variant_diversity import variant_diversity

CGA_SCORERS = [
    creative_compliance,
    character_limits,
    variant_diversity,
    brand_voice_match,
    cta_effectiveness,
]

__all__ = [
    "CGA_SCORERS",
    "creative_compliance",
    "character_limits",
    "variant_diversity",
    "brand_voice_match",
    "cta_effectiveness",
]
