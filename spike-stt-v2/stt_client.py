"""Google Cloud Speech-to-Text v2 streaming client for the A-01 spike.

Wraps the synchronous gRPC client and bridges to asyncio via a
background thread, following the fleet pattern used in
creative-generation-agent-svc/app/services/gcs_client.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Iterator

from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    """A single transcript result from STT v2."""

    text: str
    is_final: bool
    confidence: float
    speaker_tag: int
    stability: float
    result_end_offset_ms: float


@dataclass
class STTConfig:
    """Configuration for the STT v2 streaming session."""

    project_id: str
    location: str = "us-central1"
    recognizer_id: str = "oia-spike-en-us"
    credentials_json: str = ""
    credentials_path: str = ""


# Sentinel to signal end of audio stream
_STOP = object()


def _build_client(config: STTConfig) -> SpeechClient:
    """Build a SpeechClient using the 3-tier credential pattern."""
    if config.credentials_json:
        info = json.loads(config.credentials_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        return SpeechClient(credentials=credentials)
    elif config.credentials_path:
        return SpeechClient.from_service_account_file(config.credentials_path)
    else:
        # ADC fallback
        return SpeechClient()


def _recognizer_name(config: STTConfig) -> str:
    """Build the full recognizer resource name."""
    return (
        f"projects/{config.project_id}"
        f"/locations/{config.location}"
        f"/recognizers/{config.recognizer_id}"
    )


class STTStreamingSession:
    """A single STT v2 bidirectional streaming session.

    Runs the synchronous gRPC stream in a background thread and
    exposes results via an async iterator.
    """

    def __init__(self, config: STTConfig) -> None:
        self.config = config
        self._client = _build_client(config)
        self._recognizer = _recognizer_name(config)
        self._audio_queue: queue.Queue = queue.Queue(maxsize=500)
        self._result_queue: asyncio.Queue[TranscriptResult | None] = asyncio.Queue()
        self._stream_thread: threading.Thread | None = None
        self._running = False
        self._stream_id = str(uuid.uuid4())
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def stream_id(self) -> str:
        """Unique identifier for the current gRPC stream."""
        return self._stream_id

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the background streaming thread."""
        self._loop = loop
        self._running = True
        self._stream_thread = threading.Thread(
            target=self._run_stream,
            daemon=True,
            name=f"stt-stream-{self._stream_id[:8]}",
        )
        self._stream_thread.start()
        logger.info("STT stream started: %s", self._stream_id)

    def feed_audio(self, pcm_bytes: bytes) -> None:
        """Feed a chunk of LINEAR16 PCM audio into the stream."""
        if self._running:
            try:
                self._audio_queue.put_nowait(pcm_bytes)
            except queue.Full:
                logger.warning("Audio queue full, dropping chunk")

    async def results(self) -> AsyncIterator[TranscriptResult]:
        """Async iterator over transcript results."""
        while True:
            result = await self._result_queue.get()
            if result is None:
                break
            yield result

    def reconnect(self) -> None:
        """Force-close the current stream and open a new one.

        Used to test speaker label stability across reconnects (AC-2).
        """
        logger.info("Reconnect requested for stream %s", self._stream_id)
        self._running = False
        # Drain the audio queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        self._audio_queue.put(_STOP)

        if self._stream_thread:
            self._stream_thread.join(timeout=5.0)

        # Reset for new stream
        self._audio_queue = queue.Queue(maxsize=500)
        self._stream_id = str(uuid.uuid4())
        self._running = True
        self._stream_thread = threading.Thread(
            target=self._run_stream,
            daemon=True,
            name=f"stt-stream-{self._stream_id[:8]}",
        )
        self._stream_thread.start()
        logger.info("STT stream reconnected: %s", self._stream_id)

    def close(self) -> None:
        """Stop the streaming session and drain queues."""
        self._running = False
        # Signal the audio generator to stop
        try:
            self._audio_queue.put_nowait(_STOP)
        except queue.Full:
            pass

        if self._stream_thread:
            self._stream_thread.join(timeout=5.0)

        # Signal the result consumer to stop
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._result_queue.put_nowait, None)

        logger.info("STT stream closed: %s", self._stream_id)

    def _audio_generator(self) -> Iterator[cloud_speech.StreamingRecognizeRequest]:
        """Generate streaming requests: config first, then audio chunks."""
        # First request carries the streaming config
        # Note: StreamingRecognize does NOT support speaker diarization.
        # Diarization is only available via batch (non-streaming) recognition.
        # This is a key finding for the A-01 spike — F-05 LIVE mode cannot
        # rely on streaming diarization; speaker attribution must use a
        # separate mechanism (e.g., voice embeddings or batch post-processing).
        streaming_config = cloud_speech.StreamingRecognitionConfig(
            config=cloud_speech.RecognitionConfig(
                explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                    encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    audio_channel_count=1,
                ),
                features=cloud_speech.RecognitionFeatures(
                    enable_automatic_punctuation=True,
                ),
            ),
            streaming_features=cloud_speech.StreamingRecognitionFeatures(
                interim_results=True,
            ),
        )

        yield cloud_speech.StreamingRecognizeRequest(
            recognizer=self._recognizer,
            streaming_config=streaming_config,
        )

        # Subsequent requests carry audio content
        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is _STOP:
                break
            yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

    def _run_stream(self) -> None:
        """Run the synchronous gRPC streaming call in a background thread."""
        try:
            responses = self._client.streaming_recognize(
                requests=self._audio_generator()
            )
            for response in responses:
                if not self._running:
                    break
                for result in response.results:
                    if not result.alternatives:
                        continue
                    alt = result.alternatives[0]

                    # Extract speaker tag from word-level info if available
                    speaker_tag = 0
                    if alt.words:
                        speaker_tag = alt.words[-1].speaker_tag

                    tr = TranscriptResult(
                        text=alt.transcript,
                        is_final=result.is_final,
                        confidence=alt.confidence,
                        speaker_tag=speaker_tag,
                        stability=result.stability,
                        result_end_offset_ms=(
                            result.result_end_offset.total_seconds() * 1000
                            if result.result_end_offset
                            else 0.0
                        ),
                    )

                    if self._loop and self._loop.is_running():
                        self._loop.call_soon_threadsafe(
                            self._result_queue.put_nowait, tr
                        )

        except Exception as e:
            logger.error("STT stream error: %s", e)
        finally:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(
                    self._result_queue.put_nowait, None
                )


def create_recognizer(
    config: STTConfig,
    recognizer_id: str,
    language_codes: list[str],
    enable_diarization: bool = True,
) -> str:
    """Create a recognizer resource (idempotent).

    Returns the full recognizer name.
    """
    client = _build_client(config)
    parent = f"projects/{config.project_id}/locations/{config.location}"
    name = f"{parent}/recognizers/{recognizer_id}"

    # Check if it already exists
    try:
        existing = client.get_recognizer(name=name)
        logger.info("Recognizer already exists: %s", name)
        return existing.name
    except Exception:
        pass

    features = cloud_speech.RecognitionFeatures(
        enable_automatic_punctuation=True,
    )
    if enable_diarization:
        features.diarization_config = cloud_speech.SpeakerDiarizationConfig(
            min_speaker_count=2,
            max_speaker_count=2,
        )

    request = cloud_speech.CreateRecognizerRequest(
        parent=parent,
        recognizer_id=recognizer_id,
        recognizer=cloud_speech.Recognizer(
            language_codes=language_codes,
            model="long",
            default_recognition_config=cloud_speech.RecognitionConfig(
                features=features,
            ),
        ),
    )

    operation = client.create_recognizer(request=request)
    recognizer = operation.result(timeout=60)
    logger.info("Created recognizer: %s", recognizer.name)
    return recognizer.name
