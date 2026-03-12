"""Tests for SKL-MRA-05: RAGContextRetrieval."""

import pytest

from app.skills.models import SkillContext
from app.skills.rag_context_retrieval import RAGContextRetrieval


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestRAGContextRetrieval:
    async def test_disabled_returns_skip(self):
        skill = RAGContextRetrieval("http://localhost:8070", enabled=False)
        result = await skill.execute({"query": "test"}, _ctx())
        assert result.success
        assert result.data["skipped"] is True

    async def test_empty_query_fails(self):
        skill = RAGContextRetrieval("http://localhost:8070", enabled=True)
        result = await skill.execute({"query": ""}, _ctx())
        assert not result.success
        assert "No query" in result.error

    async def test_meta_correct(self):
        skill = RAGContextRetrieval("http://localhost:8070")
        assert skill.meta.skill_id == "SKL-MRA-05"
        assert "VIEWER" in skill.meta.allowed_roles
