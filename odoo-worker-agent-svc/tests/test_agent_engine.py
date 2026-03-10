"""Tests for the PAOR agent engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.engine import AgentEngine
from app.agent.models import PlanOutput, ReflectionOutput, ToolCall
from app.personas.models import PersonaDefinition
from app.services.mcp_client import ToolCallResponse


@pytest.fixture
def persona():
    return PersonaDefinition(
        name="sales_manager",
        display_name="Sales Manager",
        description="Manages sales",
        domains=["crm", "sales"],
        system_prompt="You are a Sales Manager.",
        triggers=["sales order"],
    )


@pytest.fixture
def mock_gemini():
    client = MagicMock()
    client.plan = AsyncMock()
    client.reflect = AsyncMock()
    return client


@pytest.fixture
def mock_mcp():
    client = MagicMock()
    client.call_tool = AsyncMock()
    client.list_tools = AsyncMock(return_value=[])
    return client


async def test_stub_mode(persona):
    """Should return stub result when no Gemini client."""
    engine = AgentEngine(
        gemini_client=None,
        mcp_client=MagicMock(),
    )
    result = await engine.execute(
        prompt="Create a sales order",
        persona=persona,
        skill_context="",
        tenant_id="test",
        context={},
    )
    assert result.success is True
    assert result.persona_used == "sales_manager"
    assert "Stub" in result.final_answer


async def test_plan_completes_immediately(persona, mock_gemini, mock_mcp):
    """Should complete when plan says is_complete=True."""
    mock_gemini.plan.return_value = PlanOutput(
        thought="Task is clear",
        tool_calls=[],
        is_complete=True,
        final_answer="Done — no tools needed.",
    )

    engine = AgentEngine(gemini_client=mock_gemini, mcp_client=mock_mcp)
    result = await engine.execute(
        prompt="What time is it?",
        persona=persona,
        skill_context="",
        tenant_id="test",
        context={},
    )
    assert result.success is True
    assert result.total_steps == 1
    assert mock_mcp.call_tool.call_count == 0


async def test_plan_act_reflect_cycle(persona, mock_gemini, mock_mcp):
    """Should execute full PAOR cycle with tool calls."""
    # Plan returns a tool call
    mock_gemini.plan.return_value = PlanOutput(
        thought="Need to search for customer",
        tool_calls=[
            ToolCall(
                tool_name="odoo_search",
                arguments={"model": "res.partner", "domain": []},
            )
        ],
        is_complete=False,
    )

    # MCP returns success
    mock_mcp.call_tool.return_value = ToolCallResponse(
        success=True,
        data={"records": [{"id": 1, "name": "ABC Corp"}]},
        tool_name="odoo_search",
    )

    # Reflection says done
    mock_gemini.reflect.return_value = ReflectionOutput(
        reflection="Found the customer",
        is_complete=True,
        final_answer="Customer ABC Corp found with ID 1.",
    )

    engine = AgentEngine(gemini_client=mock_gemini, mcp_client=mock_mcp)
    result = await engine.execute(
        prompt="Find customer ABC",
        persona=persona,
        skill_context="",
        tenant_id="test",
        context={},
    )
    assert result.success is True
    assert "odoo_search" in result.tools_called
    assert result.total_steps == 1


async def test_max_steps_limit(persona, mock_gemini, mock_mcp):
    """Should stop after max_steps."""
    mock_gemini.plan.return_value = PlanOutput(
        thought="Need more actions",
        tool_calls=[ToolCall(tool_name="odoo_search", arguments={})],
        is_complete=False,
    )
    mock_mcp.call_tool.return_value = ToolCallResponse(
        success=True, data={}, tool_name="odoo_search"
    )
    mock_gemini.reflect.return_value = ReflectionOutput(
        reflection="Not done yet",
        is_complete=False,
    )

    engine = AgentEngine(
        gemini_client=mock_gemini,
        mcp_client=mock_mcp,
        max_steps=2,
    )
    result = await engine.execute(
        prompt="Do something complex",
        persona=persona,
        skill_context="",
        tenant_id="test",
        context={},
    )
    assert result.success is False
    assert "Max reasoning steps" in result.error
