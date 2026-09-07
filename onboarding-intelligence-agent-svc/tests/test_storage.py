"""Phase B · GCS storage provider + LOCAL_DISK_SPOOL.

Tests cover: spool write/read, size tracking, ERR-16 on overflow, drain
lifecycle (breaker open → spool → close → drain), breaker callback wiring,
concurrent drain guard, startup drain, finalize compose, deletion, and
the recording cleanup path.

The spool tests use real filesystem writes to a temp directory. Real GCS
tests are gated by ``OIA_TEST_GCS_BUCKET`` — without it they skip.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.core.errors import SpoolBoundExceeded
from app.providers.storage import (
    LANDING_PREFIX,
    StorageProvider,
    StorageUnavailable,
    register_spool_drain,
)

TENANT = "t-storage-1"
TENANT_2 = "t-storage-2"
RECORDING = "rec-001"
RECORDING_2 = "rec-002"


def _breaker(**overrides: object) -> CircuitBreaker:
    base: dict[str, object] = dict(
        name="gcs",
        failure_threshold=2,
        window_seconds=30,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=300,
        degraded_mode="LOCAL_DISK_SPOOL",
        user_message="Upload delayed — recording continues locally.",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))  # type: ignore[arg-type]


def _open_breaker() -> CircuitBreaker:
    b = _breaker(failure_threshold=1)
    b.record_failure()
    assert b.state == State.OPEN
    return b


def _provider(
    tmp_path: object,
    breaker: CircuitBreaker | None = None,
    spool_max_bytes: int = 1_000_000,
) -> StorageProvider:
    return StorageProvider(
        "test-bucket",
        breaker=breaker or _breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=spool_max_bytes,
    )


# ── Spool write ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spool_write_creates_chunk_file(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)
    data = b"audio-chunk-data"

    result = await p.upload_chunk(TENANT, RECORDING, data, seq=0)

    from pathlib import Path

    chunk = Path(str(tmp_path)) / TENANT / RECORDING / "chunk_000000.opus"
    assert chunk.exists()
    assert chunk.read_bytes() == data
    assert str(chunk) == result


@pytest.mark.asyncio
async def test_spool_multiple_chunks_ordered(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    for i in range(5):
        await p.upload_chunk(TENANT, RECORDING, f"chunk-{i}".encode(), seq=i)

    from pathlib import Path

    recording_dir = Path(str(tmp_path)) / TENANT / RECORDING
    files = sorted(recording_dir.glob("chunk_*.opus"))
    assert len(files) == 5
    assert [f.name for f in files] == [f"chunk_{i:06d}.opus" for i in range(5)]


@pytest.mark.asyncio
async def test_spool_size_tracking(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    assert p.spool_bytes == 0
    data = b"x" * 100
    await p.upload_chunk(TENANT, RECORDING, data, seq=0)
    assert p.spool_bytes == 100

    await p.upload_chunk(TENANT, RECORDING, data, seq=1)
    assert p.spool_bytes == 200


@pytest.mark.asyncio
async def test_spool_size_initializes_from_disk(tmp_path: object) -> None:
    from pathlib import Path

    recording_dir = Path(str(tmp_path)) / TENANT / RECORDING
    recording_dir.mkdir(parents=True)
    (recording_dir / "chunk_000000.opus").write_bytes(b"x" * 500)
    (recording_dir / "chunk_000001.opus").write_bytes(b"y" * 300)

    p = _provider(tmp_path, breaker=_breaker())
    assert p.spool_bytes == 0
    await p.initialize()
    assert p.spool_bytes == 800


# ── ERR-16 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spool_bound_exceeded_raises_err16(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b, spool_max_bytes=100)

    await p.upload_chunk(TENANT, RECORDING, b"x" * 50, seq=0)

    with pytest.raises(SpoolBoundExceeded) as exc_info:
        await p.upload_chunk(TENANT, RECORDING, b"y" * 60, seq=1)

    assert exc_info.value.http_status == 507
    assert "ERR-16" in str(exc_info.value)


@pytest.mark.asyncio
async def test_spool_bound_exact_limit_succeeds(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b, spool_max_bytes=100)

    await p.upload_chunk(TENANT, RECORDING, b"x" * 100, seq=0)
    assert p.spool_bytes == 100


# ── Multi-tenant spool ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spool_multi_tenant_isolation(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    await p.upload_chunk(TENANT, RECORDING, b"t1-data", seq=0)
    await p.upload_chunk(TENANT_2, RECORDING, b"t2-data", seq=0)

    from pathlib import Path

    t1_chunk = Path(str(tmp_path)) / TENANT / RECORDING / "chunk_000000.opus"
    t2_chunk = Path(str(tmp_path)) / TENANT_2 / RECORDING / "chunk_000000.opus"
    assert t1_chunk.read_bytes() == b"t1-data"
    assert t2_chunk.read_bytes() == b"t2-data"
    assert p.spool_bytes == len(b"t1-data") + len(b"t2-data")


# ── Drain ───────────────────────────────────────────────────────────


class FakeBucket:
    """In-memory GCS bucket substitute for drain and finalize tests."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self._bucket_name = "test-bucket"

    def blob(self, name: str) -> "FakeBlob":
        return FakeBlob(name, self)

    def list_blobs(self, prefix: str = "") -> list["FakeBlob"]:
        return [
            FakeBlob(name, self)
            for name in sorted(self.blobs)
            if name.startswith(prefix)
        ]

    def delete_blobs(self, blobs: list["FakeBlob"]) -> None:
        for blob in blobs:
            blob.delete()


class FakeBlob:
    def __init__(self, name: str, bucket: FakeBucket) -> None:
        self.name = name
        self._bucket = bucket
        self.content_type: str | None = None

    def upload_from_string(self, data: bytes, content_type: str = "") -> None:
        self._bucket.blobs[self.name] = data
        self.content_type = content_type

    def delete(self) -> None:
        self._bucket.blobs.pop(self.name, None)

    def compose(self, sources: list["FakeBlob"]) -> None:
        combined = b""
        for src in sources:
            combined += self._bucket.blobs.get(src.name, b"")
        self._bucket.blobs[self.name] = combined

    def patch(self) -> None:
        pass

    def generate_signed_url(self, **kwargs: object) -> str:
        return f"https://storage.googleapis.com/signed/{self.name}"


class FakeClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, name: str) -> FakeBucket:
        return self._bucket


@pytest.mark.asyncio
async def test_drain_uploads_spooled_chunks(tmp_path: object) -> None:
    """Breaker open → spool → breaker reset → drain → verify GCS."""
    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)

    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    for i in range(3):
        await p.upload_chunk(TENANT, RECORDING, f"chunk-{i}".encode(), seq=i)

    assert p.spool_bytes > 0
    assert len(bucket.blobs) == 0

    b.reset()
    drained = await p.drain_spool()

    assert drained == 3
    assert p.spool_bytes == 0
    for i in range(3):
        blob_path = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}/chunk_{i:06d}.opus"
        assert blob_path in bucket.blobs
        assert bucket.blobs[blob_path] == f"chunk-{i}".encode()


@pytest.mark.asyncio
async def test_drain_stops_on_breaker_reopen(tmp_path: object) -> None:
    """Drain stops mid-way if the breaker re-opens."""
    b = _open_breaker()
    upload_count = 0

    class ReOpenBucket(FakeBucket):
        def blob(self, name: str) -> FakeBlob:
            return ReOpenBlob(name, self)

    class ReOpenBlob(FakeBlob):
        def upload_from_string(self, data: bytes, content_type: str = "") -> None:
            nonlocal upload_count
            upload_count += 1
            super().upload_from_string(data, content_type)
            if upload_count >= 2:
                b.record_failure()
                b.record_failure()

    bucket = ReOpenBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    for i in range(5):
        await p.upload_chunk(TENANT, RECORDING, f"data-{i}".encode(), seq=i)

    b.reset()
    drained = await p.drain_spool()

    assert drained < 5
    assert p.spool_bytes > 0


@pytest.mark.asyncio
async def test_drain_multi_tenant(tmp_path: object) -> None:
    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)

    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"t1-data", seq=0)
    await p.upload_chunk(TENANT_2, RECORDING_2, b"t2-data", seq=0)

    b.reset()
    drained = await p.drain_spool()
    assert drained == 2
    assert p.spool_bytes == 0


@pytest.mark.asyncio
async def test_drain_cleans_empty_dirs(tmp_path: object) -> None:
    from pathlib import Path

    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"data", seq=0)
    b.reset()
    await p.drain_spool()

    tenant_dir = Path(str(tmp_path)) / TENANT
    assert not tenant_dir.exists()


@pytest.mark.asyncio
async def test_drain_concurrent_guard(tmp_path: object) -> None:
    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"data", seq=0)
    b.reset()

    p._draining = True
    result = await p.drain_spool()
    assert result == 0
    p._draining = False


@pytest.mark.asyncio
async def test_drain_empty_spool(tmp_path: object) -> None:
    p = _provider(tmp_path)
    drained = await p.drain_spool()
    assert drained == 0


@pytest.mark.asyncio
async def test_drain_bad_filename_deleted(tmp_path: object) -> None:
    """A chunk file with an unparseable sequence is deleted, not left behind."""
    from pathlib import Path

    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"good-data", seq=0)
    recording_dir = Path(str(tmp_path)) / TENANT / RECORDING
    bad_file = recording_dir / "chunk_badname.opus"
    bad_file.write_bytes(b"corrupt")
    spool_before = p.spool_bytes

    b.reset()
    drained = await p.drain_spool()
    assert drained == 1
    assert not bad_file.exists()
    assert p.spool_bytes < spool_before


# ── Startup drain ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_startup_drain_picks_up_leftovers(tmp_path: object) -> None:
    from pathlib import Path

    recording_dir = Path(str(tmp_path)) / TENANT / RECORDING
    recording_dir.mkdir(parents=True)
    (recording_dir / "chunk_000000.opus").write_bytes(b"leftover-1")
    (recording_dir / "chunk_000001.opus").write_bytes(b"leftover-2")

    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )
    await p.initialize()

    assert p.spool_bytes == len(b"leftover-1") + len(b"leftover-2")
    drained = await p.drain_spool()
    assert drained == 2
    assert p.spool_bytes == 0
    assert len(bucket.blobs) == 2


# ── Upload path (breaker closed) ───────────────────────────────────


@pytest.mark.asyncio
async def test_upload_chunk_to_gcs(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    result = await p.upload_chunk(TENANT, RECORDING, b"audio-data", seq=0)
    expected = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}/chunk_000000.opus"
    assert result == expected
    assert bucket.blobs[expected] == b"audio-data"


@pytest.mark.asyncio
async def test_upload_falls_back_to_spool_on_failure(tmp_path: object) -> None:
    """A GCS failure (not breaker-open) falls back to spool."""

    class FailBucket(FakeBucket):
        def blob(self, name: str) -> "FailBlob":
            return FailBlob(name, self)

    class FailBlob(FakeBlob):
        def upload_from_string(self, data: bytes, content_type: str = "") -> None:
            raise ConnectionError("GCS unreachable")

    bucket = FailBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    result = await p.upload_chunk(TENANT, RECORDING, b"fallback-data", seq=0)
    from pathlib import Path

    assert Path(result).exists()
    assert p.spool_bytes == len(b"fallback-data")


# ── Finalize ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_composes_chunks(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    for i in range(3):
        await p.upload_chunk(TENANT, RECORDING, f"part-{i}|".encode(), seq=i)

    final_path = await p.finalize(TENANT, RECORDING)
    expected_final = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus"
    assert final_path == expected_final
    assert expected_final in bucket.blobs

    for i in range(3):
        chunk_path = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}/chunk_{i:06d}.opus"
        assert chunk_path not in bucket.blobs


@pytest.mark.asyncio
async def test_finalize_empty_recording(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    result = await p.finalize(TENANT, RECORDING)
    assert result == f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus"


@pytest.mark.asyncio
async def test_finalize_breaker_open_raises(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    with pytest.raises(StorageUnavailable):
        await p.finalize(TENANT, RECORDING)


# ── Signed URL ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signed_url_generation(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    blob_path = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus"
    url = await p.signed_url(blob_path)
    assert "signed" in url
    assert blob_path in url


@pytest.mark.asyncio
async def test_signed_url_breaker_open(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    with pytest.raises(StorageUnavailable):
        await p.signed_url("some/path.opus")


# ── Deletion ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_blob(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    blob_path = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus"
    bucket.blobs[blob_path] = b"data"

    deleted = await p.delete(blob_path)
    assert deleted is True
    assert blob_path not in bucket.blobs


@pytest.mark.asyncio
async def test_delete_recording(tmp_path: object) -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    for i in range(3):
        bucket.blobs[f"{LANDING_PREFIX}/{TENANT}/{RECORDING}/chunk_{i:06d}.opus"] = (
            b"data"
        )
    bucket.blobs[f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus"] = b"final"

    count = await p.delete_recording(TENANT, RECORDING)
    assert count == 4
    assert not any(RECORDING in k for k in bucket.blobs)


@pytest.mark.asyncio
async def test_delete_breaker_open(tmp_path: object) -> None:
    b = _open_breaker()
    p = _provider(tmp_path, breaker=b)

    with pytest.raises(StorageUnavailable):
        await p.delete("some/path.opus")


# ── Breaker callback wiring ────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_spool_drain_fires_on_recovery(tmp_path: object) -> None:
    b = _open_breaker()
    bucket = FakeBucket()
    client = FakeClient(bucket)
    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"spooled", seq=0)

    register_spool_drain(b, p)
    b.reset()

    await asyncio.sleep(0.1)

    expected = f"{LANDING_PREFIX}/{TENANT}/{RECORDING}/chunk_000000.opus"
    assert expected in bucket.blobs


# ── Provider properties ─────────────────────────────────────────────


def test_configured_true(tmp_path: object) -> None:
    p = _provider(tmp_path)
    assert p.configured is True


def test_configured_false(tmp_path: object) -> None:
    p = StorageProvider(
        "",
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
    )
    assert p.configured is False


# ── Full lifecycle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_breaker_open_spool_drain_finalize(
    tmp_path: object,
) -> None:
    """Upload some chunks normally, breaker opens, spool rest, breaker
    closes, drain spool, finalize — all chunks compose into final object."""
    bucket = FakeBucket()
    client = FakeClient(bucket)
    b = _breaker(failure_threshold=1)

    p = StorageProvider(
        "test-bucket",
        breaker=b,
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
        client=client,
    )

    await p.upload_chunk(TENANT, RECORDING, b"chunk-0", seq=0)
    await p.upload_chunk(TENANT, RECORDING, b"chunk-1", seq=1)

    b.record_failure()
    assert b.state == State.OPEN

    await p.upload_chunk(TENANT, RECORDING, b"chunk-2", seq=2)
    await p.upload_chunk(TENANT, RECORDING, b"chunk-3", seq=3)

    assert p.spool_bytes == len(b"chunk-2") + len(b"chunk-3")

    b.reset()
    drained = await p.drain_spool()
    assert drained == 2
    assert p.spool_bytes == 0

    final_path = await p.finalize(TENANT, RECORDING)
    assert f"{LANDING_PREFIX}/{TENANT}/{RECORDING}.opus" == final_path
    assert final_path in bucket.blobs
    assert bucket.blobs[final_path] == b"chunk-0chunk-1chunk-2chunk-3"


# ── GCS integration (gated) ────────────────────────────────────────

GCS_BUCKET = os.environ.get("OIA_TEST_GCS_BUCKET", "")


@pytest.mark.skipif(not GCS_BUCKET, reason="OIA_TEST_GCS_BUCKET not set")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_gcs_upload_and_delete(tmp_path: object) -> None:
    """Upload a chunk to real GCS, verify it exists, delete it."""
    p = StorageProvider(
        GCS_BUCKET,
        breaker=_breaker(),
        spool_dir=str(tmp_path),
        spool_max_bytes=1_000_000,
    )

    tenant = f"test-{uuid.uuid4().hex[:8]}"
    recording = f"test-{uuid.uuid4().hex[:8]}"
    data = b"integration-test-audio-data"

    blob_path = await p.upload_chunk(tenant, recording, data, seq=0)

    from google.cloud.storage import Client

    client = Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_path)
    assert blob.exists()

    count = await p.delete_recording(tenant, recording)
    assert count >= 1
    assert not blob.exists()
