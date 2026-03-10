"""Persona loader — reads and validates persona YAML files."""

import logging
from pathlib import Path

import yaml

from app.personas.models import PersonaDefinition

logger = logging.getLogger(__name__)


def load_all_personas(
    personas_dir: str | Path = "config/personas",
) -> dict[str, PersonaDefinition]:
    """Load all persona YAML files from the given directory.

    Returns a dict mapping persona name to PersonaDefinition.
    Logs warnings for malformed files but never raises (fail-open).
    """
    directory = Path(personas_dir)
    if not directory.is_dir():
        logger.warning("Personas directory not found: %s", directory)
        return {}

    personas: dict[str, PersonaDefinition] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            persona = _parse_persona_file(path)
            if persona:
                personas[persona.name] = persona
                logger.info("Loaded persona: %s (%s)", persona.name, path.name)
        except Exception:
            logger.warning("Failed to parse persona file: %s", path, exc_info=True)

    logger.info("Loaded %d persona(s) from %s", len(personas), directory)
    return personas


def _parse_persona_file(path: Path) -> PersonaDefinition | None:
    """Parse a single persona YAML file."""
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    if not isinstance(data, dict) or "name" not in data:
        logger.warning("Persona file %s missing 'name' field", path.name)
        return None

    return PersonaDefinition(**data)
