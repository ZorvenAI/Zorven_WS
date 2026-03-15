"""Shared test fixtures for skill tests."""

import pytest

from app.skills.models import SkillContext


@pytest.fixture
def basic_skill_context():
    """Basic SkillContext for skill execution tests."""
    return SkillContext(
        session_id="test-session-001",
        tenant_id="test-tenant",
        user_role="EDITOR",
        previous_skill_results={},
        previous_outputs={},
        skill_context_text="",
        config={},
        operating_mode="external_only",
    )


@pytest.fixture
def basic_input_data():
    """Basic input_data dict for skill tests."""
    return {
        "company_name": "TestCorp",
        "prompt": "Analyze customer feedback for TestCorp",
    }
