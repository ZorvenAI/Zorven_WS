"""J-02 — Hierarchical memory compression preserving evidence spans.

Design §6 Memory. When the assembled evidence exceeds 0.75 of the model's
context window, older transcript segments are compressed to topic summaries
while evidence spans are preserved as structured metadata alongside the text.
"""

from __future__ import annotations

from typing import Any

from app.api.schemas import EvidenceSpan
from app.core.config import Settings
from app.core.logging import get_logger
from app.logic.evidence_assembler import EvidenceBlock

logger = get_logger(__name__)


async def compress_if_needed(
    blocks: list[EvidenceBlock],
    llm: Any,
    settings: Settings,
) -> tuple[list[EvidenceBlock], bool]:
    """Check the token threshold and compress if exceeded.

    Returns (possibly-compressed blocks, whether compression was applied).
    """
    if not blocks:
        return blocks, False

    token_estimate = sum(len(b.text) // 4 for b in blocks)
    threshold = int(
        getattr(settings, "CONTEXT_WINDOW_TOKENS", 1_000_000)
        * getattr(settings, "CONTEXT_SUMMARIZE_AT", 0.75)
    )

    if token_estimate <= threshold:
        logger.info(
            "compression_not_needed",
            token_estimate=token_estimate,
            threshold=threshold,
        )
        return blocks, False

    logger.info(
        "compression_triggered",
        token_estimate=token_estimate,
        threshold=threshold,
        block_count=len(blocks),
    )

    from app.providers.llm import LLMUnavailable

    try:
        compressed = await _hierarchical_summarize(blocks, llm, cutoff_age_s=600)
    except LLMUnavailable:
        logger.warning(
            "compression_llm_unavailable",
            detail="proceeding with uncompressed evidence",
        )
        return blocks, False

    actually_compressed = any(b.compressed for b in compressed)
    return compressed, actually_compressed


async def _hierarchical_summarize(
    blocks: list[EvidenceBlock],
    llm: Any,
    cutoff_age_s: float = 600,
) -> list[EvidenceBlock]:
    """Compress older blocks while keeping recent ones verbatim.

    The last ``cutoff_age_s`` seconds of transcript stay verbatim.
    Everything older is grouped by source_type and compressed via the LLM.
    Evidence spans are extracted before compression and reattached after.
    """
    if not blocks:
        return blocks

    latest_time = _latest_timestamp(blocks)
    cutoff_time = latest_time - cutoff_age_s if latest_time > 0 else 0

    recent: list[EvidenceBlock] = []
    older: list[EvidenceBlock] = []

    for block in blocks:
        if block.source_type != "transcript":
            recent.append(block)
            continue

        block_time = _block_latest_time(block)
        if block_time >= cutoff_time or block_time == 0:
            recent.append(block)
        else:
            older.append(block)

    if not older:
        return blocks

    texts, all_spans = _separate_spans(older)

    prompt = _build_summarization_prompt(texts)
    summary_text = await llm.generate(prompt, temperature=0.1)

    compressed_block = _reattach_spans(summary_text, all_spans)
    compressed_block.original_token_estimate = sum(
        b.original_token_estimate for b in older
    )

    result = [compressed_block] + recent

    original_tokens = sum(len(b.text) // 4 for b in blocks)
    compressed_tokens = sum(len(b.text) // 4 for b in result)
    logger.info(
        "compression_complete",
        older_blocks=len(older),
        recent_blocks=len(recent),
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        ratio=round(compressed_tokens / original_tokens, 3) if original_tokens else 1.0,
    )

    return result


def _latest_timestamp(blocks: list[EvidenceBlock]) -> float:
    """Find the latest t_end across all spans."""
    latest = 0.0
    for block in blocks:
        for span in block.spans:
            if span.t_end > latest:
                latest = span.t_end
    return latest


def _block_latest_time(block: EvidenceBlock) -> float:
    """The latest t_end in a single block's spans."""
    if not block.spans:
        return 0.0
    return max(s.t_end for s in block.spans)


def _separate_spans(
    blocks: list[EvidenceBlock],
) -> tuple[list[str], list[EvidenceSpan]]:
    """Extract text and flatten all spans from a set of blocks."""
    texts: list[str] = []
    all_spans: list[EvidenceSpan] = []

    for block in blocks:
        texts.append(block.text)
        all_spans.extend(block.spans)

    return texts, all_spans


def _reattach_spans(
    summary_text: str,
    spans: list[EvidenceSpan],
) -> EvidenceBlock:
    """Create a compressed block with the summarized text and all original spans."""
    return EvidenceBlock(
        text=summary_text,
        spans=spans,
        source_type="transcript",
        recording_id=None,
        compressed=True,
    )


def _build_summarization_prompt(texts: list[str]) -> str:
    """Build the prompt for hierarchical summarization."""
    combined = "\n\n---\n\n".join(texts)
    return (
        "Summarize the following meeting transcript segments into concise "
        "topic summaries. Preserve key facts, decisions, and any specific "
        "answers to questions. Group related content by topic. Keep proper "
        "nouns, numbers, and specific details. Do not invent information "
        "not present in the text.\n\n"
        f"Transcript segments:\n\n{combined}\n\n"
        "Provide a structured summary grouped by topic:"
    )
