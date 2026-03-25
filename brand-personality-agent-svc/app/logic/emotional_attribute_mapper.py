"""SKL-BPV-08: Validate per-persona emotional intensity scores."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EmotionalAttributeMapper:
    """Validate emotional attribute map (per-persona, 0-100)."""

    async def validate(self, emotional_map: dict[str, Any]) -> dict[str, Any]:
        """Validate emotional intensity scores."""
        personas = emotional_map.get("personas", [])
        validated = []

        for persona in personas:
            emotions = persona.get("emotions", [])
            validated_emotions = []
            for em in emotions:
                intensity = min(max(float(em.get("intensity", 0)), 0), 100)
                validated_emotions.append({
                    "emotion": em.get("emotion", ""),
                    "intensity": intensity,
                })
            validated.append({
                "persona": persona.get("persona", ""),
                "emotions": validated_emotions,
            })

        consistency = min(
            max(float(emotional_map.get("consistency_score", 0)), 0), 100
        )

        return {
            "personas": validated,
            "consistency_score": consistency,
        }
