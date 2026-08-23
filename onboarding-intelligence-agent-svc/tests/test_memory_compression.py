"""J-02 — Memory compression tests.

AC-2: spans survive summarization, compression triggers at 0.75 threshold.
"""

import pytest

from app.api.schemas import EvidenceSpan
from app.logic.evidence_assembler import EvidenceBlock
from app.logic.memory_compression import (
    compress_if_needed,
    _build_summarization_prompt,
    _hierarchical_summarize,
    _latest_timestamp,
    _separate_spans,
    _reattach_spans,
)

pytestmark = pytest.mark.unit


def _block(
    text: str,
    spans: list[EvidenceSpan] | None = None,
    source_type: str = "transcript",
    recording_id: str = "rec-1",
) -> EvidenceBlock:
    return EvidenceBlock(
        text=text,
        spans=spans or [],
        source_type=source_type,
        recording_id=recording_id,
        original_token_estimate=len(text) // 4,
    )


def _span(t_start: float, t_end: float, rec_id: str = "rec-1") -> EvidenceSpan:
    return EvidenceSpan(recording_id=rec_id, t_start=t_start, t_end=t_end)


class _FakeLLM:
    """Predictable LLM stand-in for compression tests."""

    def __init__(self, response: str = "Summary of the conversation."):
        self._response = response
        self.calls: list[str] = []

    async def generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        self.calls.append(prompt)
        return self._response


class _FakeSettings:
    CONTEXT_WINDOW_TOKENS = 1_000_000
    CONTEXT_SUMMARIZE_AT = 0.75


class _SmallWindowSettings:
    CONTEXT_WINDOW_TOKENS = 100
    CONTEXT_SUMMARIZE_AT = 0.75


# ── AC-2: spans survive summarization ──────────────────────────────


@pytest.mark.asyncio
async def test_spans_survive_summarization():
    """Construct blocks with known spans, compress, verify all spans preserved."""
    spans_a = [_span(0.0, 10.0), _span(10.0, 20.0)]
    spans_b = [_span(100.0, 110.0)]

    blocks = [
        _block("Early part of conversation", spans_a),
        _block("Much later part of conversation", spans_b),
    ]

    llm = _FakeLLM("Compressed topic summary.")
    compressed = await _hierarchical_summarize(blocks, llm, cutoff_age_s=50)

    all_spans = []
    for b in compressed:
        all_spans.extend(b.spans)

    original_spans = spans_a + spans_b
    assert len(all_spans) == len(original_spans)

    for original in original_spans:
        assert any(
            s.recording_id == original.recording_id
            and s.t_start == original.t_start
            and s.t_end == original.t_end
            for s in all_spans
        ), f"span {original} not found in compressed output"


@pytest.mark.asyncio
async def test_compression_at_075_threshold():
    """Evidence below threshold is not compressed; above threshold is."""
    settings = _FakeSettings()
    llm = _FakeLLM()

    small_block = _block("Short text", [_span(0.0, 5.0)])
    result, compressed = await compress_if_needed([small_block], llm, settings)
    assert not compressed
    assert result == [small_block]
    assert len(llm.calls) == 0

    settings_small = _SmallWindowSettings()
    old_block = _block("x" * 200, [_span(0.0, 10.0)])
    recent_block = _block("y" * 200, [_span(700.0, 710.0)])
    result2, compressed2 = await compress_if_needed(
        [old_block, recent_block], llm, settings_small
    )
    assert compressed2
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_verbatim_window_preserved():
    """Segments within the last 10 minutes remain verbatim after compression."""
    old_spans = [_span(0.0, 10.0)]
    recent_spans = [_span(590.0, 610.0)]

    old_block = _block("Old content from beginning", old_spans)
    recent_block = _block("Recent content just said", recent_spans)

    llm = _FakeLLM("Summarized old content.")
    compressed = await _hierarchical_summarize(
        [old_block, recent_block], llm, cutoff_age_s=600
    )

    recent_texts = [b.text for b in compressed if not b.compressed]
    assert "Recent content just said" in recent_texts


@pytest.mark.asyncio
async def test_answered_questions_collapse():
    """Non-transcript blocks (question_answer) are preserved verbatim."""
    q_block = _block(
        "Q: What is your company name?\nA: Zorven",
        source_type="question_answer",
    )
    t_block = _block("Some old transcript", [_span(0.0, 5.0)])
    recent_block = _block("Recent transcript", [_span(600.0, 610.0)])

    llm = _FakeLLM("Summary of old transcript.")
    compressed = await _hierarchical_summarize(
        [t_block, q_block, recent_block], llm, cutoff_age_s=600
    )

    q_texts = [b.text for b in compressed if b.source_type == "question_answer"]
    assert len(q_texts) == 1
    assert "Zorven" in q_texts[0]


@pytest.mark.asyncio
async def test_empty_evidence_does_not_crash():
    """Graceful handling of no blocks."""
    settings = _FakeSettings()
    llm = _FakeLLM()

    result, compressed = await compress_if_needed([], llm, settings)
    assert result == []
    assert not compressed


# ── Helper function tests ──────────────────────────────────────────


def test_latest_timestamp():
    blocks = [
        _block("a", [_span(0.0, 10.0)]),
        _block("b", [_span(5.0, 20.0), _span(15.0, 30.0)]),
    ]
    assert _latest_timestamp(blocks) == 30.0


def test_latest_timestamp_no_spans():
    blocks = [_block("a")]
    assert _latest_timestamp(blocks) == 0.0


def test_separate_spans():
    blocks = [
        _block("text1", [_span(0.0, 10.0)]),
        _block("text2", [_span(10.0, 20.0), _span(20.0, 30.0)]),
    ]
    texts, spans = _separate_spans(blocks)
    assert texts == ["text1", "text2"]
    assert len(spans) == 3


def test_reattach_spans():
    spans = [_span(0.0, 10.0), _span(10.0, 20.0)]
    block = _reattach_spans("Summary text", spans)
    assert block.text == "Summary text"
    assert block.compressed is True
    assert len(block.spans) == 2
    assert block.spans[0].t_start == 0.0


def test_build_summarization_prompt():
    prompt = _build_summarization_prompt(["Part 1", "Part 2"])
    assert "Part 1" in prompt
    assert "Part 2" in prompt
    assert "topic" in prompt.lower()


@pytest.mark.asyncio
async def test_llm_unavailable_skips_compression():
    """When LLM raises LLMUnavailable, compression is skipped."""
    from app.providers.llm import LLMUnavailable

    class _FailingLLM:
        async def generate(self, prompt: str, *, temperature: float = 0.2) -> str:
            raise LLMUnavailable("test breaker open")

    settings = _SmallWindowSettings()
    old_block = _block("x" * 200, [_span(0.0, 10.0)])
    recent_block = _block("y" * 200, [_span(700.0, 710.0)])

    result, compressed = await compress_if_needed(
        [old_block, recent_block], _FailingLLM(), settings
    )
    assert not compressed
    assert result == [old_block, recent_block]
