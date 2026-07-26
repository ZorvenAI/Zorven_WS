"""Tests for Gemini LLM client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.llm import GeminiClient
from app.agent.models import PlanOutput, ReflectionOutput


@pytest.fixture
def gemini_client():
    return GeminiClient(model_name="gemini-3.5-flash")


def test_parse_plan_response_valid(gemini_client):
    """Should parse valid plan JSON response."""
    text = json.dumps(
        {
            "thought": "I need to search for the customer",
            "tool_calls": [
                {"tool_name": "odoo_search", "arguments": {"model": "res.partner"}}
            ],
            "is_complete": False,
            "final_answer": "",
        }
    )
    result = gemini_client._parse_plan_response(text)
    assert isinstance(result, PlanOutput)
    assert result.thought == "I need to search for the customer"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "odoo_search"
    assert result.is_complete is False


def test_parse_plan_response_complete(gemini_client):
    """Should handle completed plan response."""
    text = json.dumps(
        {
            "thought": "Task is straightforward",
            "tool_calls": [],
            "is_complete": True,
            "final_answer": "The answer is 42.",
        }
    )
    result = gemini_client._parse_plan_response(text)
    assert result.is_complete is True
    assert result.final_answer == "The answer is 42."


def test_parse_plan_response_invalid(gemini_client):
    """Should handle malformed JSON gracefully."""
    result = gemini_client._parse_plan_response("not json at all")
    assert isinstance(result, PlanOutput)
    assert result.is_complete is True  # Fallback


def test_parse_reflect_response_valid(gemini_client):
    """Should parse valid reflection JSON."""
    text = json.dumps(
        {
            "reflection": "Customer was found successfully",
            "is_complete": True,
            "final_answer": "Customer ABC Corp found.",
            "next_actions": [],
        }
    )
    result = gemini_client._parse_reflect_response(text)
    assert isinstance(result, ReflectionOutput)
    assert result.is_complete is True
    assert "ABC Corp" in result.final_answer


def test_parse_reflect_response_needs_more(gemini_client):
    """Should handle reflection that needs more actions."""
    text = json.dumps(
        {
            "reflection": "Need to create the order next",
            "is_complete": False,
            "final_answer": "",
            "next_actions": [
                {"tool_name": "sales_create_order", "arguments": {"partner_id": 1}}
            ],
        }
    )
    result = gemini_client._parse_reflect_response(text)
    assert result.is_complete is False
    assert len(result.next_actions) == 1


def test_parse_reflect_response_invalid(gemini_client):
    """Should handle malformed reflection JSON gracefully."""
    result = gemini_client._parse_reflect_response("broken")
    assert isinstance(result, ReflectionOutput)
    assert result.is_complete is True  # Fallback


def test_max_tool_calls_enforced(gemini_client):
    """Should cap tool calls at max_tool_calls_per_step."""
    gemini_client._max_tool_calls_per_step = 2
    text = json.dumps(
        {
            "thought": "Many actions",
            "tool_calls": [
                {"tool_name": f"tool_{i}", "arguments": {}} for i in range(10)
            ],
            "is_complete": False,
        }
    )
    result = gemini_client._parse_plan_response(text)
    assert len(result.tool_calls) <= 2


async def test_build_plan_prompt(gemini_client):
    """Should build a well-structured plan prompt."""
    prompt = await gemini_client._build_plan_prompt(
        persona_prompt="You are a Sales Manager.",
        skill_context="## Skills\n- Create orders",
        observation_history="",
        available_tools=[{"name": "odoo_search", "description": "Search records"}],
    )
    assert "Sales Manager" in prompt
    assert "odoo_search" in prompt
    assert "Skills" in prompt
