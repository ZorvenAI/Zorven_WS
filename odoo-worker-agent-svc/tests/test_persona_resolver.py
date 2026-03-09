"""Tests for persona resolver."""

from pathlib import Path

import pytest

from app.personas.loader import load_all_personas
from app.personas.models import PersonaDefinition
from app.personas.resolver import PersonaResolver

PERSONAS_DIR = Path(__file__).parent.parent / "config" / "personas"


@pytest.fixture
def personas():
    return load_all_personas(PERSONAS_DIR)


@pytest.fixture
def resolver(personas):
    return PersonaResolver(personas=personas, gemini_client=None)


async def test_keyword_match_sales(resolver):
    """Should resolve sales_manager for sales-related prompts."""
    persona = await resolver.resolve("Create a sales order for customer ABC")
    assert persona.name == "sales_manager"


async def test_keyword_match_accounting(resolver):
    """Should resolve accountant for invoice prompts."""
    persona = await resolver.resolve("Create an invoice for the client")
    assert persona.name == "accountant"


async def test_keyword_match_inventory(resolver):
    """Should resolve warehouse_manager for inventory prompts."""
    persona = await resolver.resolve("What are the current inventory and stock levels")
    assert persona.name == "warehouse_manager"


async def test_keyword_match_hr(resolver):
    """Should resolve hr_manager for leave/employee prompts."""
    persona = await resolver.resolve("Approve leave request for John")
    assert persona.name == "hr_manager"


async def test_fallback_to_general_assistant(resolver):
    """Should fall back to general_assistant for unmatched prompts."""
    persona = await resolver.resolve("xyzzy foobar baz")
    assert persona.name == "general_assistant"


async def test_empty_personas_fallback():
    """Should return synthetic fallback when no personas loaded."""
    resolver = PersonaResolver(personas={}, gemini_client=None)
    persona = await resolver.resolve("anything")
    assert persona.name == "general_assistant"


async def test_priority_ordering(resolver):
    """Higher-priority personas should win on equal trigger matches."""
    # "balance sheet" and "reconciliation" trigger financial_controller
    persona = await resolver.resolve("Prepare the balance sheet and reconciliation")
    assert persona.name == "financial_controller"


async def test_resolve_with_context(resolver):
    """Context dict should not break resolution."""
    persona = await resolver.resolve("Create a sales order", context={"extra": "data"})
    assert isinstance(persona, PersonaDefinition)
