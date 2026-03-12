"""Tests for SKL-MRA-07: RAGStoreIndexer."""

import pytest

from app.skills.models import SkillContext
from app.skills.rag_store_indexer import RAGStoreIndexer


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestRAGStoreIndexer:
    async def test_disabled_returns_skip(self):
        skill = RAGStoreIndexer("http://localhost:8070", enabled=False)
        result = await skill.execute({"content": "test"}, _ctx())
        assert result.success
        assert result.data["skipped"] is True

    async def test_no_content_fails(self):
        skill = RAGStoreIndexer("http://localhost:8070", enabled=True)
        result = await skill.execute({"content": ""}, _ctx())
        assert not result.success
        assert "No content" in result.error

    async def test_meta_correct(self):
        skill = RAGStoreIndexer("http://localhost:8070")
        assert skill.meta.skill_id == "SKL-MRA-07"
        assert "VIEWER" not in skill.meta.allowed_roles
