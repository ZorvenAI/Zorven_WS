"""Tests for persona loader."""

from pathlib import Path

from app.personas.loader import load_all_personas
from app.personas.models import PersonaDefinition

PERSONAS_DIR = Path(__file__).parent.parent / "config" / "personas"


def test_load_all_personas():
    """Should load all 14 persona YAML files."""
    personas = load_all_personas(PERSONAS_DIR)
    assert len(personas) >= 14
    assert all(isinstance(p, PersonaDefinition) for p in personas.values())


def test_persona_names():
    """Each persona should have a unique snake_case name."""
    personas = load_all_personas(PERSONAS_DIR)
    names = list(personas.keys())
    assert len(names) == len(set(names))
    for name in names:
        assert "_" in name or name.isalpha()


def test_general_assistant_exists():
    """general_assistant must exist as the fallback persona."""
    personas = load_all_personas(PERSONAS_DIR)
    assert "general_assistant" in personas
    ga = personas["general_assistant"]
    assert ga.priority == 1


def test_persona_required_fields():
    """Each persona should have all required fields populated."""
    personas = load_all_personas(PERSONAS_DIR)
    for name, persona in personas.items():
        assert persona.name, f"{name} missing name"
        assert persona.display_name, f"{name} missing display_name"
        assert persona.description, f"{name} missing description"
        assert persona.domains, f"{name} missing domains"
        assert persona.triggers, f"{name} missing triggers"
        assert persona.system_prompt, f"{name} missing system_prompt"


def test_load_nonexistent_dir():
    """Should return empty dict for nonexistent directory."""
    personas = load_all_personas("/nonexistent/path")
    assert personas == {}


def test_persona_priorities():
    """Priorities should be in valid range."""
    personas = load_all_personas(PERSONAS_DIR)
    for name, persona in personas.items():
        assert 1 <= persona.priority <= 10, f"{name} priority out of range"
