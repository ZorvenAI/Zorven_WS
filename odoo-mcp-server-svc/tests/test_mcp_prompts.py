"""Tests for MCP prompts."""

from app.mcp.prompts import PromptRegistry


class TestPromptRegistry:
    def test_list_prompts_returns_8(self):
        registry = PromptRegistry()
        prompts = registry.list_prompts()
        assert len(prompts) == 8

    def test_prompt_names(self):
        registry = PromptRegistry()
        prompts = registry.list_prompts()
        names = {p.name for p in prompts}
        assert "order_to_cash" in names
        assert "procure_to_pay" in names
        assert "month_end_close" in names
        assert "tenant_setup_wizard" in names

    async def test_get_known_prompt(self):
        registry = PromptRegistry()
        result = await registry.get_prompt(
            "order_to_cash", {"customer_name": "Acme Corp"}
        )
        assert result.description != ""
        assert len(result.messages) == 1
        assert "Acme Corp" in result.messages[0].content.text

    async def test_get_unknown_prompt(self):
        registry = PromptRegistry()
        result = await registry.get_prompt("nonexistent")
        assert "Unknown prompt" in result.description
        assert len(result.messages) == 0

    async def test_get_prompt_with_defaults(self):
        registry = PromptRegistry()
        result = await registry.get_prompt("month_end_close", {"period": "2024-12"})
        assert "2024-12" in result.messages[0].content.text
