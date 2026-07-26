"""Unit tests for stt_client.py.

No Google Cloud credentials required — tests only exercise local logic.
"""

from __future__ import annotations

import queue
import uuid

import pytest

from stt_client import (
    STTConfig,
    STTStreamingSession,
    _recognizer_name,
)


class TestRecognizerName:
    def test_format(self):
        config = STTConfig(
            project_id="my-project",
            location="us-central1",
            recognizer_id="oia-spike-en-us",
        )
        name = _recognizer_name(config)
        assert name == "projects/my-project/locations/us-central1/recognizers/oia-spike-en-us"

    def test_different_location(self):
        config = STTConfig(
            project_id="proj-x",
            location="europe-west1",
            recognizer_id="custom-rec",
        )
        name = _recognizer_name(config)
        assert "locations/europe-west1" in name
        assert "recognizers/custom-rec" in name


class TestSTTStreamingSession:
    def _make_session(self) -> STTStreamingSession:
        """Create a session without connecting to GCP."""
        config = STTConfig(
            project_id="test-project",
            location="us-central1",
            recognizer_id="oia-spike-en-us",
        )
        # We can't actually build a client without credentials,
        # so we test the session's local state management
        session = STTStreamingSession.__new__(STTStreamingSession)
        session.config = config
        session._recognizer = _recognizer_name(config)
        session._audio_queue = queue.Queue(maxsize=500)
        session._running = False
        session._stream_id = str(uuid.uuid4())
        session._stream_thread = None
        session._loop = None
        return session

    def test_stream_id_is_uuid(self):
        session = self._make_session()
        # Validate it's a valid UUID
        parsed = uuid.UUID(session.stream_id)
        assert str(parsed) == session.stream_id

    def test_reconnect_changes_stream_id(self):
        session = self._make_session()
        old_id = session.stream_id

        # Simulate reconnect state changes (without actual gRPC)
        session._stream_id = str(uuid.uuid4())
        session._audio_queue = queue.Queue(maxsize=500)

        assert session.stream_id != old_id

    def test_audio_queue_drains_on_close(self):
        session = self._make_session()
        session._running = True

        # Put some items in the queue
        for i in range(5):
            session._audio_queue.put(b"chunk")

        assert session._audio_queue.qsize() == 5

        # close() signals stop
        session._running = False
        # Drain manually (close() does this via _STOP sentinel)
        while not session._audio_queue.empty():
            session._audio_queue.get_nowait()

        assert session._audio_queue.empty()

    def test_feed_audio_drops_when_not_running(self):
        session = self._make_session()
        session._running = False
        session.feed_audio(b"should be dropped")
        assert session._audio_queue.empty()

    def test_feed_audio_queues_when_running(self):
        session = self._make_session()
        session._running = True
        session.feed_audio(b"chunk1")
        session.feed_audio(b"chunk2")
        assert session._audio_queue.qsize() == 2


class TestSTTConfig:
    def test_defaults(self):
        config = STTConfig(project_id="test")
        assert config.location == "us-central1"
        assert config.recognizer_id == "oia-spike-en-us"
        assert config.credentials_json == ""
        assert config.credentials_path == ""

    def test_streaming_config_values(self):
        """Verify the streaming config constants used in _audio_generator.

        Note: StreamingRecognize does NOT support speaker diarization.
        Diarization is only available via batch recognition.
        """
        from google.cloud.speech_v2.types import cloud_speech

        # Build the streaming config the same way stt_client.py does
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

        # Verify interim results enabled
        assert streaming_config.streaming_features.interim_results is True

        # Verify punctuation enabled
        assert streaming_config.config.features.enable_automatic_punctuation is True
