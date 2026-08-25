"""J-02 — Evidence assembly for PROCESS mode.

Gathers every piece of evidence a session produced — transcripts, media OCR,
question state with evidence spans, unmapped batches — into a single working
context for extraction. Fetches the canonical data from Django, enriches with
Redis state when keys are still within the 4h TTL window.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from app.api.schemas import EvidenceManifest, EvidenceSpan
from app.cache.redis_manager import RedisManager
from app.cache.retry_queue import queue_size
from app.core.config import Settings
from app.core.logging import get_logger
from app.services.backend_client import BackendClient

logger = get_logger(__name__)


@dataclass
class EvidenceBlock:
    """One chunk of evidence with its provenance."""

    text: str
    spans: list[EvidenceSpan] = field(default_factory=list)
    source_type: str = "transcript"
    recording_id: str | None = None
    compressed: bool = False
    original_token_estimate: int = 0


@dataclass
class AssembledEvidence:
    """The complete working context for extraction."""

    blocks: list[EvidenceBlock] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    missing_media: list[str] = field(default_factory=list)
    degraded_question_ids: list[str] = field(default_factory=list)
    token_estimate: int = 0
    compressed: bool = False
    compression_ratio: float = 1.0
    rag_chunks: list[EvidenceBlock] = field(default_factory=list)
    company_id: int | None = None


class EvidenceAssembler:
    """Gather session evidence from Django and Redis into a working context."""

    def __init__(
        self,
        redis: RedisManager,
        backend: BackendClient | None,
        settings: Settings,
    ) -> None:
        self._redis = redis
        self._backend = backend
        self._settings = settings
        self._questions: list[dict[str, Any]] = []

    async def assemble(
        self,
        *,
        tenant_id: str,
        session_id: str,
        manifest: EvidenceManifest,
    ) -> AssembledEvidence:
        """Orchestrate the full evidence assembly."""
        django_data = await self._fetch_from_django(tenant_id, session_id)
        redis_questions = await self._load_redis_questions(tenant_id, session_id)

        questions = self._merge_questions(
            django_data.get("questions", []) if django_data else [],
            redis_questions,
        )
        self._questions = questions

        missing_media = await self._check_pending_ocr(tenant_id, session_id)

        if django_data and django_data.get("ocr_pending_count", 0) > 0:
            await_result = await self._await_pending_ocr(
                tenant_id, session_id, self._settings.OCR_AWAIT_TIMEOUT_S
            )
            missing_media.extend(await_result)

        blocks = self._build_blocks(django_data, redis_questions)
        degraded = self._mark_degraded_questions(questions)

        token_estimate = self._estimate_tokens(blocks)

        if not self.rag_chunks:
            logger.debug(
                "rag_retrieval_not_implemented",
                session_id=session_id,
            )

        company_id = None
        if django_data and isinstance(django_data, dict):
            company_id = django_data.get("company_id")

        evidence = AssembledEvidence(
            blocks=blocks,
            questions=questions,
            missing_media=missing_media,
            degraded_question_ids=degraded,
            token_estimate=token_estimate,
            rag_chunks=[],
            company_id=company_id,
        )

        logger.info(
            "evidence_assembled",
            session_id=session_id,
            block_count=len(blocks),
            question_count=len(questions),
            missing_media_count=len(missing_media),
            degraded_count=len(degraded),
            token_estimate=token_estimate,
            django_available=django_data is not None,
            redis_questions_available=len(redis_questions) > 0,
        )

        return evidence

    @property
    def rag_chunks(self) -> list[EvidenceBlock]:
        return []

    def question_states_for_coverage(self) -> list[dict[str, Any]]:
        """Return the merged question list for coverage computation."""
        return self._questions

    async def _fetch_from_django(
        self, tenant_id: str, session_id: str
    ) -> dict[str, Any] | None:
        """Fetch the evidence bundle from Django's internal endpoint."""
        if self._backend is None:
            logger.warning("evidence_no_backend", session_id=session_id)
            return None

        result = await self._backend.get_session_evidence(
            tenant_id=tenant_id, session_id=session_id
        )

        if result is None:
            logger.warning(
                "evidence_django_unavailable",
                session_id=session_id,
                detail="backend returned None — breaker open or network error",
            )
            return None

        if isinstance(result, dict) and result.get("__status__") == 404:
            logger.warning(
                "evidence_session_not_found",
                session_id=session_id,
                detail="Django returned 404 for session evidence",
            )
            return None

        return result

    async def _load_redis_questions(
        self, tenant_id: str, session_id: str
    ) -> dict[str, dict[str, Any]]:
        """Load question state from Redis if keys are still live."""
        keys = self._redis.keys_for(tenant_id)
        q_key = keys.questions(session_id)

        try:
            raw = await self._redis.client.hgetall(  # type: ignore[misc,unused-ignore]
                q_key
            )
        except Exception:
            logger.warning("evidence_redis_questions_failed", session_id=session_id)
            return {}

        if not raw:
            return {}

        result: dict[str, dict[str, Any]] = {}
        for raw_qid, raw_val in raw.items():
            qid = str(raw_qid)
            val = str(raw_val) if not isinstance(raw_val, str) else raw_val
            try:
                result[qid] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                continue

        logger.info(
            "evidence_redis_questions_loaded",
            session_id=session_id,
            count=len(result),
        )
        return result

    def _merge_questions(
        self,
        django_questions: list[dict[str, Any]],
        redis_questions: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge Django and Redis question data, preferring Redis for live fields."""
        if not django_questions and not redis_questions:
            return []

        if not redis_questions:
            return django_questions

        if not django_questions:
            result: list[dict[str, Any]] = []
            for qid, rq in redis_questions.items():
                q = {**rq, "question_id": qid}
                result.append(q)
            return result

        merged: list[dict[str, Any]] = []
        django_by_id: dict[str, dict[str, Any]] = {}
        for q in django_questions:
            qid = str(q.get("id", ""))
            if qid:
                django_by_id[qid] = q

        seen: set[str] = set()
        for qid, rq in redis_questions.items():
            dq = django_by_id.get(qid, {})
            m = {**dq, **rq}
            m["question_id"] = qid
            merged.append(m)
            seen.add(qid)

        for qid, dq in django_by_id.items():
            if qid not in seen:
                dq["question_id"] = qid
                merged.append(dq)

        return merged

    async def _check_pending_ocr(self, tenant_id: str, session_id: str) -> list[str]:
        """Check the OCR retry queue for pending items."""
        keys = self._redis.keys_for(tenant_id)
        try:
            pending = await queue_size(self._redis.client, keys)
        except Exception:
            logger.warning("evidence_ocr_queue_check_failed", session_id=session_id)
            return []

        if pending > 0:
            logger.info(
                "evidence_ocr_pending",
                session_id=session_id,
                pending_count=pending,
            )

        return []

    async def _await_pending_ocr(
        self, tenant_id: str, session_id: str, timeout_s: int
    ) -> list[str]:
        """Wait up to timeout_s for pending OCR items to complete.

        Returns media_ids of items still pending after the timeout.
        Only polls queue_size — never dequeues, since the OCR retry
        pipeline owns item lifecycle.
        """
        keys = self._redis.keys_for(tenant_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        poll_interval = 5.0

        while loop.time() < deadline:
            pending = await queue_size(self._redis.client, keys)
            if pending == 0:
                return []

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))

        final_pending = await queue_size(self._redis.client, keys)
        if final_pending > 0:
            logger.warning(
                "evidence_ocr_timeout",
                session_id=session_id,
                still_pending=final_pending,
                timeout_s=timeout_s,
            )

            from app.cache.retry_queue import OCRRetryItem

            key = keys.retry_queue("ocr")
            try:
                raw_items = await self._redis.client.zrange(key, 0, -1)
                return [
                    OCRRetryItem.from_json(
                        r.decode() if isinstance(r, bytes) else str(r)
                    ).media_id
                    for r in raw_items
                ]
            except Exception:
                return []

        return []

    def _build_blocks(
        self,
        django_data: dict[str, Any] | None,
        redis_questions: dict[str, dict[str, Any]],
    ) -> list[EvidenceBlock]:
        """Construct the evidence block list from all sources."""
        blocks: list[EvidenceBlock] = []

        if django_data:
            blocks.extend(self._blocks_from_recordings(django_data))
            blocks.extend(self._blocks_from_media(django_data))

        blocks.extend(self._blocks_from_merged_questions())

        return blocks

    def _blocks_from_recordings(
        self, django_data: dict[str, Any]
    ) -> list[EvidenceBlock]:
        """Build evidence blocks from recording transcripts."""
        blocks: list[EvidenceBlock] = []

        for rec in django_data.get("recordings", []):
            recording_id = str(rec.get("id", ""))
            transcript = rec.get("transcript")

            if not transcript or not isinstance(transcript, list):
                continue

            segments_text: list[str] = []
            spans: list[EvidenceSpan] = []

            for seg in transcript:
                text = seg.get("text", "").strip()
                if not text:
                    continue

                segments_text.append(text)

                t_start = seg.get("t_start")
                t_end = seg.get("t_end")
                if t_start is not None and t_end is not None:
                    spans.append(
                        EvidenceSpan(
                            recording_id=recording_id,
                            t_start=float(t_start),
                            t_end=float(t_end),
                        )
                    )

            if segments_text:
                full_text = "\n".join(segments_text)
                blocks.append(
                    EvidenceBlock(
                        text=full_text,
                        spans=spans,
                        source_type="transcript",
                        recording_id=recording_id,
                        original_token_estimate=len(full_text) // 4,
                    )
                )

            summary = rec.get("summary")
            if summary and isinstance(summary, dict):
                summary_text = summary.get("text", "")
                if summary_text:
                    blocks.append(
                        EvidenceBlock(
                            text=summary_text,
                            spans=[],
                            source_type="recording_summary",
                            recording_id=recording_id,
                            original_token_estimate=len(summary_text) // 4,
                        )
                    )

        return blocks

    def _blocks_from_media(self, django_data: dict[str, Any]) -> list[EvidenceBlock]:
        """Build evidence blocks from media OCR text."""
        blocks: list[EvidenceBlock] = []

        for media in django_data.get("media", []):
            ocr_text = media.get("ocr_text")
            if not ocr_text or not ocr_text.strip():
                continue

            if media.get("rag_excluded", False):
                continue

            blocks.append(
                EvidenceBlock(
                    text=ocr_text.strip(),
                    spans=[],
                    source_type="media_ocr",
                    recording_id=None,
                    original_token_estimate=len(ocr_text) // 4,
                )
            )

        return blocks

    def _blocks_from_merged_questions(self) -> list[EvidenceBlock]:
        """Build evidence blocks from the authoritative merged question list."""
        blocks: list[EvidenceBlock] = []

        for q in self._questions:
            status = q.get("status", "OPEN")
            if status != "GREEN":
                continue

            answer = q.get("answer_summary", "")
            if not answer:
                continue

            evidence_raw = q.get("evidence", [])
            spans: list[EvidenceSpan] = []
            if isinstance(evidence_raw, list):
                for e in evidence_raw:
                    if isinstance(e, dict) and all(
                        k in e for k in ("recording_id", "t_start", "t_end")
                    ):
                        spans.append(
                            EvidenceSpan(
                                recording_id=str(e["recording_id"]),
                                t_start=float(e["t_start"]),
                                t_end=float(e["t_end"]),
                            )
                        )

            text = f"Q: {q.get('text', '')}\nA: {answer}"
            blocks.append(
                EvidenceBlock(
                    text=text,
                    spans=spans,
                    source_type="question_answer",
                    recording_id=None,
                    original_token_estimate=len(text) // 4,
                )
            )

        return blocks

    def _mark_degraded_questions(self, questions: list[dict[str, Any]]) -> list[str]:
        """AC-4: questions marked GREEN manually with no evidence spans."""
        degraded: list[str] = []

        for q in questions:
            if q.get("status") != "GREEN":
                continue

            source = q.get("source", "")
            evidence = q.get("evidence", [])

            if source == "manual" and not evidence:
                qid = q.get("question_id", q.get("id", ""))
                degraded.append(str(qid))
                logger.info(
                    "evidence_degraded_question",
                    question_id=qid,
                    detail="manual GREEN with no evidence spans",
                )

        return degraded

    @staticmethod
    def _estimate_tokens(blocks: list[EvidenceBlock]) -> int:
        """Approximate token count as chars/4."""
        return sum(len(b.text) // 4 for b in blocks)
