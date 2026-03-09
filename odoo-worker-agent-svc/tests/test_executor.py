"""Tests for the WorkerExecutor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.models import AgentResult, ReasoningStep
from app.api.schemas import ExecuteRequest
from app.personas.models import PersonaDefinition
from app.services.executor import WorkerExecutor


@pytest.fixture
def mock_persona_resolver():
    resolver = MagicMock()
    resolver.resolve = AsyncMock(
        return_value=PersonaDefinition(
            name="sales_manager",
            display_name="Sales Manager",
            description="Manages sales",
            domains=["crm"],
            system_prompt="You are a Sales Manager.",
            triggers=["sales order"],
        )
    )
    return resolver


@pytest.fixture
def mock_skill_router():
    router = MagicMock()
    router.resolve_skills_for_persona.return_value = {
        "worker_skill_context": "## Skills",
        "worker_skill_names": ["create-sales-order"],
        "suggested_mcp_tools": ["odoo_search"],
    }
    return router


@pytest.fixture
def mock_agent_engine():
    engine = MagicMock()
    engine.execute = AsyncMock(
        return_value=AgentResult(
            persona_used="sales_manager",
            reasoning_steps=[
                ReasoningStep(step_number=1, phase="plan", thought="Done")
            ],
            final_answer="Sales order created.",
            findings=["Order SO001 created"],
            recommendations=[],
            tools_called=["odoo_search", "sales_create_order"],
            total_steps=1,
            success=True,
        )
    )
    return engine


@pytest.fixture
def executor(mock_persona_resolver, mock_skill_router, mock_agent_engine):
    return WorkerExecutor(
        persona_resolver=mock_persona_resolver,
        skill_router=mock_skill_router,
        agent_engine=mock_agent_engine,
    )


async def test_execute_success(executor):
    """Should execute successfully and return proper response."""
    request = ExecuteRequest(
        input_prompt="Create a sales order for customer ABC",
        tenant_context={"user_roles": ["sales_manager"]},
    )
    response = await executor.execute(request, "test-tenant")
    assert response.status == "success"
    assert response.persona_used == "sales_manager"
    assert "odoo_search" in response.tools_called
    assert response.reasoning_steps == 1


async def test_execute_rate_limited():
    """Should return error when rate limited."""
    mock_redis = MagicMock()
    mock_redis.check_rate_limit = AsyncMock(return_value=False)

    executor = WorkerExecutor(
        persona_resolver=MagicMock(),
        skill_router=MagicMock(),
        agent_engine=MagicMock(),
        redis_manager=mock_redis,
    )
    request = ExecuteRequest(input_prompt="anything")
    response = await executor.execute(request, "test-tenant")
    assert response.status == "error"
    assert "Rate limit" in response.error


async def test_execute_handles_exception(executor, mock_agent_engine):
    """Should handle exceptions gracefully."""
    mock_agent_engine.execute = AsyncMock(side_effect=RuntimeError("something broke"))
    request = ExecuteRequest(input_prompt="Create order")
    response = await executor.execute(request, "test-tenant")
    assert response.status == "error"
    assert response.error is not None
