"""Speech-to-text provider — ABC plus the Google STT v2 implementation.

Design §8.4, §4.3, §9.2 · implemented by story F-05.

Two implementations from day one (F-05 technical note #3): the Google client
and a fixture-driven fake. The fake replays timings from a JSONL file so every
test above the adapter layer gets deterministic, free, fast results without
touching the network.

Spike A-01 established that STT v2 StreamingRecognize does NOT support speaker
diarization. Speaker attribution is deferred to a follow-up story; all segments
carry speaker=0.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

DEPENDENCY = "stt"
OVERLAP_S = 5.0


class STTUnavailable(Exception):
    """Speech-to-text could not be performed. Carries the operator-facing reason."""

    def __init__(self, reason: str, *, degraded_mode: str = "RECORD_ONLY") -> None:
        super().__init__(reason)
        self.reason = reason
        self.degraded_mode = degraded_mode


@dataclass
class STTResult:
    """One result from the STT stream — partial or final."""

    text: str
    is_final: bool
    t_start: float
    t_end: float
    stability: float


class STTAdapter(ABC):
    """The interface both implementations share.

    ``stream()`` accepts an async iterator of raw audio bytes and yields
    ``STTResult`` objects. Rollover, reconnection and dedup are internal
    concerns — the caller sees a single continuous stream.
    """

    @abstractmethod
    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16000,
        codec: str = "LINEAR16",
        language: str = "en-US",
    ) -> AsyncIterator[STTResult]:
        yield  # type: ignore[misc]


def _dedup_key(result: STTResult) -> tuple[float, str]:
    """Key for deduplicating finals across stream rollover."""
    return (round(result.t_start, 1), result.text[:40].strip().lower())


# ── Google STT v2 ────────────────────────────────────────────────────


class GoogleSTTAdapter(STTAdapter):
    """Real STT v2 streaming with circuit breaker and stream rollover.

    Lazy client initialisation follows ``llm.py``'s pattern: the
    ``SpeechAsyncClient`` is created on first use and held for the process
    lifetime.

    Stream rollover (AC-3): at ``stream_limit_s`` seconds, a new Google
    stream opens with a 5-second audio overlap. Finals in the overlap
    window are deduplicated by ``(round(t_start, 1), text[:40])`` so the
    operator sees neither a gap nor a duplicate.
    """

    def __init__(
        self,
        *,
        project: str,
        location: str = "global",
        recognizer: str = "_",
        credentials_path: str = "",
        stream_limit_s: int = 280,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._recognizer = (
            f"projects/{project}/locations/{location}/recognizers/{recognizer}"
        )
        self._credentials_path = credentials_path
        self._stream_limit_s = stream_limit_s
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._project)

    def _ensure_client(self) -> Any:
        """Create the async client on first use and hold it.

        Mirrors ``llm.py``'s held-owner pattern — letting the client be
        garbage-collected between calls closed it, and every subsequent
        call failed with "client has been closed".
        """
        if self._client is None:
            from google.cloud.speech_v2 import SpeechAsyncClient

            kwargs: dict[str, Any] = {}
            if self._credentials_path:
                from google.oauth2 import service_account

                kwargs["credentials"] = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
                    self._credentials_path
                )
            self._client = SpeechAsyncClient(**kwargs)
        return self._client

    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16000,
        codec: str = "LINEAR16",
        language: str = "en-US",
    ) -> AsyncIterator[STTResult]:
        if not self.configured:
            raise STTUnavailable("no GCP project configured for STT")

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise STTUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
                degraded_mode=exc.degraded_mode,
            ) from exc

        try:
            async for result in self._stream_with_rollover(
                audio, sample_rate=sample_rate, codec=codec, language=language
            ):
                yield result
            self._breaker.record_success()
        except STTUnavailable:
            self._breaker.record_failure()
            raise
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("stt_stream_failed", error=f"{type(exc).__name__}: {exc}")
            raise STTUnavailable(f"stream failed: {type(exc).__name__}") from exc

    async def _stream_with_rollover(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int,
        codec: str,
        language: str,
    ) -> AsyncIterator[STTResult]:
        from google.cloud.speech_v2.types import cloud_speech as cs

        config = cs.StreamingRecognitionConfig(
            config=cs.RecognitionConfig(
                explicit_decoding_config=cs.ExplicitDecodingConfig(
                    encoding=self._encoding_for(codec),
                    sample_rate_hertz=sample_rate,
                    audio_channel_count=1,
                ),
                language_codes=[language],
                model="long",
                features=cs.RecognitionFeatures(enable_word_time_offsets=True),
            ),
            streaming_features=cs.StreamingRecognitionFeatures(
                interim_results=True,
            ),
        )

        result_q: asyncio.Queue[STTResult | Exception | None] = asyncio.Queue()
        seen: set[tuple[float, str]] = set()
        current_feed: asyncio.Queue[bytes | None] = asyncio.Queue()
        stream_start = time.monotonic()

        task = asyncio.create_task(
            self._stream_worker(current_feed, result_q, config=config, offset_s=0.0)
        )

        overlap_feed: asyncio.Queue[bytes | None] | None = None
        overlap_task: asyncio.Task[None] | None = None
        rolling_over = False
        overlap_started_at = 0.0

        try:
            async for chunk in audio:
                elapsed = time.monotonic() - stream_start
                current_feed.put_nowait(chunk)

                if not rolling_over and elapsed >= self._stream_limit_s:
                    rolling_over = True
                    overlap_started_at = time.monotonic()
                    overlap_feed = asyncio.Queue()
                    overlap_feed.put_nowait(chunk)
                    overlap_task = asyncio.create_task(
                        self._stream_worker(
                            overlap_feed,
                            result_q,
                            config=config,
                            offset_s=elapsed,
                        )
                    )
                    logger.info("stt_rollover_started", elapsed_s=round(elapsed, 1))

                elif rolling_over and overlap_feed is not None:
                    overlap_feed.put_nowait(chunk)
                    if time.monotonic() - overlap_started_at >= OVERLAP_S:
                        current_feed.put_nowait(None)
                        await task
                        assert overlap_task is not None
                        task = overlap_task
                        current_feed = overlap_feed
                        overlap_feed = None
                        overlap_task = None
                        rolling_over = False
                        stream_start = time.monotonic()
                        logger.info("stt_rollover_completed")

                async for r in self._drain_q(result_q, seen):
                    yield r

            current_feed.put_nowait(None)
            if overlap_feed is not None:
                overlap_feed.put_nowait(None)

            await task
            if overlap_task is not None:
                await overlap_task

            async for r in self._drain_q(result_q, seen):
                yield r

        finally:
            for t in [task, overlap_task]:
                if t is not None and not t.done():
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

    async def _stream_worker(
        self,
        audio_q: asyncio.Queue[bytes | None],
        result_q: asyncio.Queue[STTResult | Exception | None],
        *,
        config: Any,
        offset_s: float,
    ) -> None:
        """One STT v2 bidirectional stream: reads audio_q, writes result_q."""
        from google.cloud.speech_v2.types import cloud_speech as cs

        async def _requests() -> AsyncIterator[Any]:
            yield cs.StreamingRecognizeRequest(
                recognizer=self._recognizer, streaming_config=config
            )
            while True:
                chunk = await audio_q.get()
                if chunk is None:
                    return
                yield cs.StreamingRecognizeRequest(audio=chunk)

        client = self._ensure_client()
        try:
            responses = await client.streaming_recognize(requests=_requests())
            async for response in responses:
                for result in response.results:
                    if not result.alternatives:
                        continue
                    alt = result.alternatives[0]
                    t_start, t_end = self._timestamps(result, alt, offset_s)
                    await result_q.put(
                        STTResult(
                            text=alt.transcript,
                            is_final=result.is_final,
                            t_start=t_start,
                            t_end=t_end,
                            stability=getattr(
                                result,
                                "stability",
                                1.0 if result.is_final else 0.5,
                            ),
                        )
                    )
        except Exception as exc:
            await result_q.put(exc)

    @staticmethod
    def _timestamps(result: Any, alt: Any, offset_s: float) -> tuple[float, float]:
        words = getattr(alt, "words", None)
        if words:
            t_start = words[0].start_offset.total_seconds() + offset_s
            t_end = words[-1].end_offset.total_seconds() + offset_s
            return t_start, t_end
        end = getattr(result, "result_end_offset", None)
        t_end = end.total_seconds() + offset_s if end else offset_s
        return t_end, t_end

    @staticmethod
    async def _drain_q(
        result_q: asyncio.Queue[STTResult | Exception | None],
        seen: set[tuple[float, str]],
    ) -> AsyncIterator[STTResult]:
        while not result_q.empty():
            item = result_q.get_nowait()
            if item is None:
                continue
            if isinstance(item, Exception):
                raise item
            if item.is_final:
                key = _dedup_key(item)
                if key in seen:
                    continue
                seen.add(key)
            yield item

    @staticmethod
    def _encoding_for(codec: str) -> Any:
        from google.cloud.speech_v2.types import cloud_speech as cs

        mapping = {
            "LINEAR16": cs.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            "WEBM_OPUS": cs.ExplicitDecodingConfig.AudioEncoding.WEBM_OPUS,
            "OGG_OPUS": cs.ExplicitDecodingConfig.AudioEncoding.OGG_OPUS,
        }
        return mapping.get(
            codec.upper(),
            cs.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
        )


# ── Fixture-driven fake ─────────────────────────────────────────────


class FakeSTTAdapter(STTAdapter):
    """Replays events from a JSONL fixture or a provided event list.

    Used by every test above the adapter layer. The events carry text,
    timing and a ``delay_ms`` that simulates real-world pacing. The fake
    consumes (and discards) the audio iterator in the background so callers
    that produce audio are not blocked.
    """

    def __init__(
        self,
        fixture_path: Path | str | None = None,
        *,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        if events is not None:
            self._events = events
        elif fixture_path is not None:
            self._events = self._load(Path(fixture_path))
        else:
            self._events = []

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16000,
        codec: str = "LINEAR16",
        language: str = "en-US",
    ) -> AsyncIterator[STTResult]:
        drain_task = asyncio.create_task(self._drain_audio(audio))
        try:
            for event in self._events:
                delay = event.get("delay_ms", 50) / 1000.0
                await asyncio.sleep(delay)
                yield STTResult(
                    text=event["text"],
                    is_final=event["is_final"],
                    t_start=event["t_start"],
                    t_end=event["t_end"],
                    stability=event.get("stability", 1.0 if event["is_final"] else 0.5),
                )
        finally:
            if not drain_task.done():
                drain_task.cancel()
                try:
                    await drain_task
                except asyncio.CancelledError:
                    pass

    @staticmethod
    async def _drain_audio(audio: AsyncIterator[bytes]) -> None:
        async for _ in audio:
            pass
