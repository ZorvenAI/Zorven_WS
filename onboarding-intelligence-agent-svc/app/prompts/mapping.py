"""OIA internal prompt IDs to POI catalog names.

The mapping exists because the design uses short dotted IDs (oia.research_brief)
while POI's naming convention is zorven-<service>-<skill>. Neither should change
to match the other.

Design §17.1 · implemented by story L-01.
"""

from __future__ import annotations

PROMPT_MAP: dict[str, str] = {
    "oia.research_brief": "zorven-oia-research-brief",
    "oia.generate_questionnaire": "zorven-oia-questionnaire",
    "oia.analyze_stream": "zorven-oia-analyze-stream",
    "oia.sufficiency": "zorven-oia-sufficiency",
    "oia.followups": "zorven-oia-followups",
    "oia.media_analysis": "zorven-oia-media-analysis",
    "oia.media_analysis_multi": "zorven-oia-media-analysis-multi",
    "oia.summarize_recording": "zorven-oia-summarize-recording",
    "oia.extract_fields": "zorven-oia-extract-fields",
}

ALL_PROMPT_IDS: tuple[str, ...] = tuple(PROMPT_MAP.keys())

PREP_PROMPTS: frozenset[str] = frozenset(
    {
        "oia.research_brief",
        "oia.generate_questionnaire",
    }
)

LIVE_PROMPTS: frozenset[str] = frozenset(
    {
        "oia.analyze_stream",
        "oia.sufficiency",
        "oia.followups",
        "oia.media_analysis",
        "oia.media_analysis_multi",
    }
)

PROCESS_PROMPTS: frozenset[str] = frozenset(
    {
        "oia.summarize_recording",
        "oia.extract_fields",
    }
)


def poi_name(prompt_id: str) -> str:
    """Resolve an internal prompt ID to the POI catalog name."""
    name = PROMPT_MAP.get(prompt_id)
    if name is None:
        raise ValueError(f"Unknown prompt_id: {prompt_id}")
    return name
