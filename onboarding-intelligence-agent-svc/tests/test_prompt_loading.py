"""L-05 AC-3 — fallback prompts must stay in sync with their consuming skills.

Each fallback in ``fallbacks.py`` is documented as "verbatim from the skill
file that owns it." If a skill's prompt changes and the fallback is not
updated, the agent falls back to a stale prompt that may no longer produce
parseable output. These tests catch that drift in CI.

``oia.extract_fields`` is a special case: the prompt is built dynamically per
wizard page by ``FieldExtractor._build_prompt()``, so the fallback is a
structural scaffold — the test asserts required JSON format landmarks.
"""

from __future__ import annotations

import importlib

import pytest

from app.prompts.fallbacks import get_fallback_prompts
from app.prompts.mapping import ALL_PROMPT_IDS

pytestmark = pytest.mark.unit

SKILL_CONSTANTS: dict[str, tuple[str, str]] = {
    "oia.research_brief": ("app.skills.research_business", "PROMPT"),
    "oia.generate_questionnaire": ("app.skills.generate_questionnaire", "PROMPT"),
    "oia.analyze_stream": (
        "app.skills.analyze_transcript_stream",
        "_SYSTEM_PROMPT",
    ),
    "oia.sufficiency": (
        "app.skills.evaluate_answer_sufficiency",
        "_SYSTEM_PROMPT",
    ),
    "oia.followups": ("app.skills.generate_followups", "_SYSTEM_PROMPT"),
    "oia.media_analysis": ("app.providers.vision", "ANALYSIS_PROMPT"),
    "oia.media_analysis_multi": ("app.providers.vision", "MULTI_FRAME_PROMPT"),
    "oia.summarize_recording": ("app.skills.summarize_recording", "PROMPT_TEMPLATE"),
}

PLACEHOLDER_VARS: dict[str, dict[str, str]] = {
    "oia.research_brief": {
        "company_name": "TestCo",
        "website": "https://example.com",
        "industry": "retail",
        "notes": "none",
        "sources": "Source A",
    },
    "oia.generate_questionnaire": {
        "facts": "[]",
        "unknowns": "[]",
        "company_name": "TestCo",
        "notes": "none",
        "count": "12",
        "depth_guidance": "standard",
        "vocabulary": "name, industry",
        "wf3_min": "3",
    },
    "oia.media_analysis": {"ocr_text": "Sample OCR text"},
    "oia.media_analysis_multi": {"ocr_text": "Sample OCR text from frames"},
    "oia.summarize_recording": {"transcript": "Speaker 1: Hello."},
}


@pytest.mark.parametrize("prompt_id", list(SKILL_CONSTANTS.keys()))
def test_all_fallbacks_schema_valid(prompt_id: str):
    """Each fallback template matches its skill's prompt constant.

    A mismatch means the skill's prompt was changed without updating the
    fallback, and a degraded session would use a stale prompt that may
    produce output the skill's parser cannot handle.
    """
    mod_path, const_name = SKILL_CONSTANTS[prompt_id]
    mod = importlib.import_module(mod_path)
    skill_prompt = getattr(mod, const_name)

    fallback = get_fallback_prompts()[prompt_id]

    assert skill_prompt.strip() == fallback.strip(), (
        f"Fallback for {prompt_id} has drifted from {mod_path}.{const_name}. "
        "Update fallbacks.py to match the skill's current prompt."
    )


@pytest.mark.parametrize(
    "prompt_id",
    list(PLACEHOLDER_VARS.keys()),
)
def test_fallback_placeholders_are_formattable(prompt_id: str):
    """Templates with {placeholders} can be formatted without KeyError."""
    template = get_fallback_prompts()[prompt_id]
    variables = PLACEHOLDER_VARS[prompt_id]
    formatted = template.format(**variables)
    assert len(formatted) > 0


def test_extract_fields_fallback_has_required_format():
    """The extract_fields fallback contains the expected JSON format block."""
    template = get_fallback_prompts()["oia.extract_fields"]

    for landmark in ("fields", "field_name", "value", "confidence", "evidence"):
        assert (
            f'"{landmark}"' in template
        ), f'extract_fields fallback is missing JSON key "{landmark}"'


def test_all_prompt_ids_covered():
    """Every prompt ID in ALL_PROMPT_IDS has either a skill constant mapping
    or a structural landmark test (extract_fields)."""
    covered = set(SKILL_CONSTANTS.keys()) | {"oia.extract_fields"}
    assert covered == set(
        ALL_PROMPT_IDS
    ), f"Uncovered prompt IDs: {set(ALL_PROMPT_IDS) - covered}"
