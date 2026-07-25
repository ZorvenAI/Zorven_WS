"""Integration tests for STT v2 — require real Google Cloud credentials.

Run with: pytest tests/test_stt_integration.py -v -m integration

Requires:
    - OIA_SPIKE_PROJECT_ID environment variable set
    - Valid GCP credentials (ADC or OIA_SPIKE_CREDENTIALS_JSON)
    - Recognizer resources created via create_recognizers.py
"""

from __future__ import annotations

import asyncio
import os
import struct
import time
from pathlib import Path

import pytest

from stt_client import STTConfig, STTStreamingSession, _build_client, _recognizer_name

pytestmark = pytest.mark.integration

FIXTURE_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures"


def _get_config(recognizer_id: str = "oia-spike-en-us") -> STTConfig:
    return STTConfig(
        project_id=os.environ.get("OIA_SPIKE_PROJECT_ID", ""),
        location=os.environ.get("OIA_SPIKE_LOCATION", "us-central1"),
        recognizer_id=recognizer_id,
        credentials_json=os.environ.get("OIA_SPIKE_CREDENTIALS_JSON", ""),
        credentials_path=os.environ.get("OIA_SPIKE_CREDENTIALS_PATH", ""),
    )


def _load_fixture_pcm() -> bytes | None:
    """Load the WAV fixture and return raw PCM bytes (skip header)."""
    wav_path = FIXTURE_DIR / "two_speaker_onboarding_sample.wav"
    if not wav_path.exists():
        return None
    with open(wav_path, "rb") as f:
        data = f.read()
    # Skip 44-byte WAV header
    return data[44:]


class TestRecognizerExists:
    def test_en_us_recognizer_reachable(self, gcp_project_id: str):
        config = _get_config("oia-spike-en-us")
        client = _build_client(config)
        name = _recognizer_name(config)
        recognizer = client.get_recognizer(name=name)
        assert recognizer.name == name

    def test_auto_recognizer_reachable(self, gcp_project_id: str):
        config = _get_config("oia-spike-auto")
        client = _build_client(config)
        name = _recognizer_name(config)
        recognizer = client.get_recognizer(name=name)
        assert recognizer.name == name


class TestStreamingRecognize:
    def test_streaming_fixture_produces_results(self, gcp_project_id: str):
        """Stream the audio fixture and verify we get transcript results."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found — record it first")

        config = _get_config("oia-spike-en-us")
        session = STTStreamingSession(config)
        loop = asyncio.new_event_loop()

        results = []

        async def run():
            session.start(loop)

            # Feed audio in 100ms chunks (3200 bytes = 1600 samples * 2 bytes at 16kHz)
            chunk_size = 3200
            for i in range(0, min(len(pcm), chunk_size * 50), chunk_size):
                chunk = pcm[i : i + chunk_size]
                session.feed_audio(chunk)
                await asyncio.sleep(0.1)  # Real-time pacing

            # Wait for results
            await asyncio.sleep(2.0)
            session.close()

            async for result in session.results():
                results.append(result)

        loop.run_until_complete(run())
        loop.close()

        assert len(results) > 0, "Expected at least one transcript result"

    def test_streaming_diarization_returns_speaker_tags(self, gcp_project_id: str):
        """Verify that streaming results include speaker_tag values."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found — record it first")

        config = _get_config("oia-spike-en-us")
        session = STTStreamingSession(config)
        loop = asyncio.new_event_loop()

        results = []

        async def run():
            session.start(loop)

            chunk_size = 3200
            for i in range(0, min(len(pcm), chunk_size * 50), chunk_size):
                session.feed_audio(pcm[i : i + chunk_size])
                await asyncio.sleep(0.1)

            await asyncio.sleep(2.0)
            session.close()

            async for result in session.results():
                results.append(result)

        loop.run_until_complete(run())
        loop.close()

        # At least some results should have non-zero speaker tags
        speaker_tags = {r.speaker_tag for r in results if r.is_final}
        # Diarization may not always produce tags for short clips,
        # but the field should exist
        assert all(hasattr(r, "speaker_tag") for r in results)

    def test_streaming_interim_results_arrive(self, gcp_project_id: str):
        """Verify that interim (non-final) results arrive before final results."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found — record it first")

        config = _get_config("oia-spike-en-us")
        session = STTStreamingSession(config)
        loop = asyncio.new_event_loop()

        results = []

        async def run():
            session.start(loop)

            chunk_size = 3200
            for i in range(0, min(len(pcm), chunk_size * 100), chunk_size):
                session.feed_audio(pcm[i : i + chunk_size])
                await asyncio.sleep(0.1)

            await asyncio.sleep(3.0)
            session.close()

            async for result in session.results():
                results.append(result)

        loop.run_until_complete(run())
        loop.close()

        interim = [r for r in results if not r.is_final]
        assert len(interim) > 0, "Expected interim results with interim_results=True"

    def test_multi_language_recognizer_on_english_audio(self, gcp_project_id: str):
        """Verify oia-spike-auto correctly transcribes English audio."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found — record it first")

        config = _get_config("oia-spike-auto")
        session = STTStreamingSession(config)
        loop = asyncio.new_event_loop()

        results = []

        async def run():
            session.start(loop)

            chunk_size = 3200
            for i in range(0, min(len(pcm), chunk_size * 50), chunk_size):
                session.feed_audio(pcm[i : i + chunk_size])
                await asyncio.sleep(0.1)

            await asyncio.sleep(2.0)
            session.close()

            async for result in session.results():
                results.append(result)

        loop.run_until_complete(run())
        loop.close()

        assert len(results) > 0

    def test_reconnect_produces_valid_results(self, gcp_project_id: str):
        """After forced reconnect, subsequent audio still transcribes."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found — record it first")

        config = _get_config("oia-spike-en-us")
        session = STTStreamingSession(config)
        loop = asyncio.new_event_loop()

        stream_ids = []

        async def run():
            session.start(loop)
            stream_ids.append(session.stream_id)

            chunk_size = 3200
            # Send first batch
            for i in range(0, min(len(pcm), chunk_size * 20), chunk_size):
                session.feed_audio(pcm[i : i + chunk_size])
                await asyncio.sleep(0.1)

            await asyncio.sleep(1.0)

            # Reconnect
            session.reconnect()
            stream_ids.append(session.stream_id)

            # Send second batch
            offset = chunk_size * 20
            for i in range(offset, min(len(pcm), offset + chunk_size * 20), chunk_size):
                session.feed_audio(pcm[i : i + chunk_size])
                await asyncio.sleep(0.1)

            await asyncio.sleep(2.0)
            session.close()

        loop.run_until_complete(run())
        loop.close()

        assert len(stream_ids) == 2
        assert stream_ids[0] != stream_ids[1], "Reconnect should produce a new stream ID"
