"""G-04 · SKL-OIA-06, targeted follow-up question generation.

No mocks. The skill is driven through a real LLMProvider with a local
stand-in for the model, same pattern as test_sufficiency.py.
"""

from __future__ import annotations

import json

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.providers.llm import LLMProvider, LLMUnavailable
from app.skills.generate_followups import GenerateFollowups
from app.skills.models import SkillContext, SkillMeta, TenantContext


def meta() -> SkillMeta:
    return SkillMeta(
        skill_id="SKL-OIA-06",
        name="generate_followups",
        description="follow-up generation",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
    )


def context(**overrides) -> SkillContext:
    input_context = {
        "question": "When was the company founded?",
        "missing_aspects": ["founding year"],
        "conversation_tone": "professional",
        "already_asked": [],
    }
    input_context.update(overrides.pop("input_context", {}))
    return SkillContext(
        input_prompt="Generate follow-up questions",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
        config=overrides.pop("config", {}),
        **overrides,
    )


def brk() -> CircuitBreaker:
    return CircuitBreaker(
        BreakerConfig(
            name="llm",
            failure_threshold=3,
            window_seconds=60,
            success_threshold=1,
            half_open_max_calls=1,
            reset_timeout_seconds=60,
            degraded_mode="MANUAL_CHECKBOXES",
            user_message="unavailable",
        )
    )


class StubModels:
    """Stand-in for ``genai.Client(...).aio.models``."""

    def __init__(self, text: str = "", raises: Exception | None = None) -> None:
        self._text = text
        self._raises = raises
        self.prompts: list[str] = []

    async def generate_content(self, *, model, contents, config=None):
        self.prompts.append(contents)
        if self._raises:
            raise self._raises

        class Response:
            text = self._text

        return Response()


def llm_for(model: StubModels) -> LLMProvider:
    return LLMProvider("k", breaker=brk(), client=model)


async def _collect(skill, ctx):
    chunks = []
    async for chunk in skill.stream(ctx):
        chunks.append(chunk)
    return chunks


GOOD_RESPONSE = json.dumps(
    [
        {
            "text": "Can you recall the year you started?",
            "addresses_aspect": "founding year",
            "priority": 1,
        },
    ]
)

TWO_FOLLOWUPS = json.dumps(
    [
        {
            "text": "Can you recall the year you started?",
            "addresses_aspect": "founding year",
            "priority": 1,
        },
        {
            "text": "Who else was involved at the beginning?",
            "addresses_aspect": "co-founders",
            "priority": 2,
        },
    ]
)

FIVE_FOLLOWUPS = json.dumps(
    [
        {"text": f"Follow-up {i}", "addresses_aspect": f"aspect {i}", "priority": i}
        for i in range(1, 6)
    ]
)


# ── Happy path ────────────────────────────────────────────────────────


async def test_skill_generates_followups():
    """SKL-OIA-06 returns follow-ups for a question with missing_aspects."""
    model = StubModels(text=TWO_FOLLOWUPS)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    assert len(chunks) == 1
    assert chunks[0]["type"] == "followup_suggestions"
    suggestions = chunks[0]["suggestions"]
    assert len(suggestions) == 2
    assert suggestions[0]["text"] == "Can you recall the year you started?"
    assert suggestions[0]["addresses_aspect"] == "founding year"


async def test_skill_no_followups_when_no_missing():
    """Empty missing_aspects yields nothing — AC-1."""
    model = StubModels(text=GOOD_RESPONSE)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    ctx = context(input_context={"missing_aspects": []})
    chunks = await _collect(skill, ctx)

    assert chunks == []
    assert model.prompts == [], "LLM should not be called"


async def test_skill_caps_at_three():
    """Even if the LLM returns 5, only 3 are kept."""
    model = StubModels(text=FIVE_FOLLOWUPS)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    assert len(chunks) == 1
    assert len(chunks[0]["suggestions"]) == 3


async def test_followup_addresses_specific_gap():
    """Output addresses_aspect references a real aspect from the input."""
    model = StubModels(text=GOOD_RESPONSE)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    suggestions = chunks[0]["suggestions"]
    assert suggestions[0]["addresses_aspect"] == "founding year"


async def test_skill_respects_already_asked():
    """The already_asked list is included in the prompt to the LLM."""
    model = StubModels(text=GOOD_RESPONSE)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    ctx = context(input_context={"already_asked": ["What year did you begin?"]})
    await _collect(skill, ctx)

    assert "What year did you begin?" in model.prompts[0]


async def test_followups_sorted_by_priority():
    """Suggestions are sorted by priority field."""
    unsorted = json.dumps(
        [
            {"text": "Low priority", "addresses_aspect": "a", "priority": 3},
            {"text": "High priority", "addresses_aspect": "b", "priority": 1},
            {"text": "Mid priority", "addresses_aspect": "c", "priority": 2},
        ]
    )
    model = StubModels(text=unsorted)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    suggestions = chunks[0]["suggestions"]
    assert suggestions[0]["text"] == "High priority"
    assert suggestions[1]["text"] == "Mid priority"
    assert suggestions[2]["text"] == "Low priority"


# ── Degradation ───────────────────────────────────────────────────────


async def test_bad_json_degrades():
    """Unparseable LLM response yields empty suggestions, no crash."""
    model = StubModels(text="This is not JSON at all")
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    assert len(chunks) == 1
    assert chunks[0]["suggestions"] == []


async def test_markdown_fences_stripped():
    """JSON wrapped in markdown fences is still parsed."""
    fenced = f"```json\n{GOOD_RESPONSE}\n```"
    model = StubModels(text=fenced)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    suggestions = chunks[0]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["text"] == "Can you recall the year you started?"


async def test_no_llm_raises():
    """No LLM provider configured raises LLMUnavailable."""
    skill = GenerateFollowups(meta(), llm=None)

    with pytest.raises(LLMUnavailable, match="no LLM provider configured"):
        await _collect(skill, context())


async def test_malformed_items_filtered():
    """Items without a 'text' field are silently dropped."""
    partial = json.dumps(
        [
            {"addresses_aspect": "year", "priority": 1},
            {"text": "Valid question?", "addresses_aspect": "year", "priority": 2},
            {"text": "", "addresses_aspect": "year", "priority": 3},
        ]
    )
    model = StubModels(text=partial)
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    suggestions = chunks[0]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["text"] == "Valid question?"


async def test_non_array_response_yields_empty():
    """An LLM returning a JSON object instead of an array yields empty."""
    model = StubModels(text='{"text": "just an object"}')
    skill = GenerateFollowups(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())

    assert chunks[0]["suggestions"] == []
