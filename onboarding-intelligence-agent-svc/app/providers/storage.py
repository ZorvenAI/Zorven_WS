"""GCS upload and LOCAL_DISK_SPOOL degraded mode.

Design §8.4 · circuit_breakers.yaml ``gcs`` entry.

Audio chunks arrive one per second during a LIVE meeting. Each is written as
a separate GCS blob under a recording-scoped prefix. On finalization the
chunks are composed into a single object and the parts deleted.

When the ``gcs`` circuit breaker opens, chunks are spooled to bounded local
disk instead. A recovery callback drains the spool to GCS when the breaker
closes; a startup drain handles leftovers from a killed instance.

Cloud Run ephemeral storage is lost on instance restart — the startup drain is
best-effort, not a durability guarantee. A durable spool (Redis or GCS
multipart) would require a separate design.

All GCS and filesystem calls are wrapped in ``asyncio.to_thread`` so they
do not block the event loop during a live meeting.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
    State,
)
from app.core.errors import SpoolBoundExceeded
from app.core.logging import get_logger

logger = get_logger(__name__)

DEPENDENCY = "gcs"
LANDING_PREFIX = "_landing/oia"


class StorageUnavailable(Exception):
    """GCS could not be reached and spool is full or disabled."""

    def __init__(self, reason: str, *, degraded_mode: str = "LOCAL_DISK_SPOOL") -> None:
        super().__init__(reason)
        self.reason = reason
        self.degraded_mode = degraded_mode


class StorageProvider:
    """GCS chunk upload with LOCAL_DISK_SPOOL degraded mode.

    Parameters
    ----------
    bucket_name : str
        The GCS bucket for recording uploads.
    breaker : CircuitBreaker | None
        The ``gcs`` circuit breaker.
    spool_dir : str
        Root directory for the local disk spool.
    spool_max_bytes : int
        Maximum total bytes across all recordings in the spool.
    signed_url_expiry_s : int
        Lifetime of signed URLs in seconds.
    client : Any | None
        Injected ``storage.Client`` for testing.
    """

    def __init__(
        self,
        bucket_name: str,
        *,
        breaker: CircuitBreaker | None = None,
        spool_dir: str = "/tmp/oia-spool",
        spool_max_bytes: int = 524_288_000,
        signed_url_expiry_s: int = 3600,
        client: Any | None = None,
    ) -> None:
        self._bucket_name = bucket_name
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._spool_dir = Path(spool_dir)
        self._spool_max_bytes = spool_max_bytes
        self._signed_url_expiry_s = signed_url_expiry_s
        self._client = client
        self._bucket: Any | None = None
        self._draining = False
        self._spool_lock = asyncio.Lock()
        self._spool_bytes = 0

    async def initialize(self) -> None:
        """Measure the existing spool size off the event loop."""
        self._spool_bytes = await asyncio.to_thread(self._measure_spool_size)

    @property
    def configured(self) -> bool:
        return bool(self._bucket_name)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google.cloud.storage import Client

            self._client = Client()
        return self._client

    def _ensure_bucket(self) -> Any:
        if self._bucket is None:
            client = self._ensure_client()
            self._bucket = client.bucket(self._bucket_name)
        return self._bucket

    def _chunk_path(self, tenant_id: str, recording_id: str, seq: int) -> str:
        return f"{LANDING_PREFIX}/{tenant_id}/{recording_id}/chunk_{seq:06d}.opus"

    def _final_path(self, tenant_id: str, recording_id: str) -> str:
        return f"{LANDING_PREFIX}/{tenant_id}/{recording_id}.opus"

    # ── Upload ──────────────────────────────────────────────────────

    async def upload_chunk(
        self,
        tenant_id: str,
        recording_id: str,
        data: bytes,
        seq: int,
    ) -> str:
        """Upload one audio chunk. Returns the GCS blob path or spool file path.

        On breaker open, spools to local disk. On spool bound exceeded, raises
        ``SpoolBoundExceeded`` (ERR-16).
        """
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen:
            return await self._spool_chunk(tenant_id, recording_id, data, seq)

        blob_path = self._chunk_path(tenant_id, recording_id, seq)
        try:
            bucket = self._ensure_bucket()
            blob = bucket.blob(blob_path)
            await asyncio.to_thread(
                blob.upload_from_string, data, content_type="audio/opus"
            )
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "gcs_upload_failed",
                tenant=tenant_id,
                recording=recording_id,
                seq=seq,
                error=str(exc),
            )
            return await self._spool_chunk(tenant_id, recording_id, data, seq)

        self._breaker.record_success()
        return blob_path

    async def finalize(
        self,
        tenant_id: str,
        recording_id: str,
    ) -> str:
        """Compose all chunks into a single final blob, then delete the parts.

        Returns the GCS path of the final composed object.

        GCS compose handles up to 32 sources per call; for larger recordings
        the composition is done recursively.
        """
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise StorageUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
            ) from exc

        try:
            bucket = self._ensure_bucket()
            prefix = f"{LANDING_PREFIX}/{tenant_id}/{recording_id}/chunk_"
            blobs = sorted(
                await asyncio.to_thread(lambda: list(bucket.list_blobs(prefix=prefix))),
                key=lambda b: b.name,
            )

            if not blobs:
                self._breaker.record_success()
                return self._final_path(tenant_id, recording_id)

            final_path = self._final_path(tenant_id, recording_id)
            composed = await asyncio.to_thread(
                self._compose_recursive, bucket, blobs, final_path
            )

            await asyncio.to_thread(self._delete_blobs_batch, bucket, blobs)

        except StorageUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            raise StorageUnavailable(f"finalization failed: {exc}") from exc

        self._breaker.record_success()
        return str(composed.name)

    @staticmethod
    def _delete_blobs_batch(bucket: Any, blobs: list[Any]) -> None:
        """Delete blobs using batch request where available, else one by one."""
        try:
            bucket.delete_blobs(blobs)
        except Exception:
            for blob in blobs:
                try:
                    blob.delete()
                except Exception:
                    pass

    def _compose_recursive(self, bucket: Any, blobs: list[Any], dest_path: str) -> Any:
        """Compose blobs into one, handling the 32-source GCS limit."""
        max_compose = 32
        if len(blobs) <= max_compose:
            dest = bucket.blob(dest_path)
            dest.compose(blobs)
            dest.content_type = "audio/opus"
            dest.patch()
            return dest

        intermediates: list[Any] = []
        for i in range(0, len(blobs), max_compose):
            batch = blobs[i : i + max_compose]
            intermediate_path = f"{dest_path}.part_{i:04d}"
            intermediate = bucket.blob(intermediate_path)
            intermediate.compose(batch)
            intermediates.append(intermediate)

        result = self._compose_recursive(bucket, intermediates, dest_path)

        for intermediate in intermediates:
            try:
                intermediate.delete()
            except Exception:
                pass

        return result

    # ── Signed URLs ─────────────────────────────────────────────────

    async def signed_url(
        self,
        blob_path: str,
        expiry_seconds: int | None = None,
    ) -> str:
        """Mint a short-lived signed URL for playback."""
        import datetime

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise StorageUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
            ) from exc

        try:
            bucket = self._ensure_bucket()
            blob = bucket.blob(blob_path)
            expiry = (
                expiry_seconds
                if expiry_seconds is not None
                else self._signed_url_expiry_s
            )
            url = await asyncio.to_thread(
                blob.generate_signed_url,
                expiration=datetime.timedelta(seconds=expiry),
                method="GET",
            )
        except StorageUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            raise StorageUnavailable(f"signed URL generation failed: {exc}") from exc

        self._breaker.record_success()
        return str(url)

    # ── Deletion (GDPR) ────────────────────────────────────────────

    async def delete(self, blob_path: str) -> bool:
        """Delete a GCS object. Returns True on success, False if not found."""
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise StorageUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
            ) from exc

        try:
            bucket = self._ensure_bucket()
            blob = bucket.blob(blob_path)
            await asyncio.to_thread(blob.delete)
        except StorageUnavailable:
            raise
        except Exception as exc:
            if _is_not_found(exc):
                self._breaker.record_success()
                return False
            self._breaker.record_failure()
            raise StorageUnavailable(f"deletion failed: {exc}") from exc

        self._breaker.record_success()
        return True

    async def delete_recording(self, tenant_id: str, recording_id: str) -> int:
        """Delete all objects for a recording (chunks + final). Returns count."""
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise StorageUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
            ) from exc

        try:
            bucket = self._ensure_bucket()
            prefix = f"{LANDING_PREFIX}/{tenant_id}/{recording_id}"
            blobs = await asyncio.to_thread(
                lambda: list(bucket.list_blobs(prefix=prefix))
            )
            count = len(blobs)
            if blobs:
                await asyncio.to_thread(self._delete_blobs_batch, bucket, blobs)
        except StorageUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            raise StorageUnavailable(f"recording deletion failed: {exc}") from exc

        self._breaker.record_success()
        return count

    # ── LOCAL_DISK_SPOOL ────────────────────────────────────────────

    async def _spool_chunk(
        self,
        tenant_id: str,
        recording_id: str,
        data: bytes,
        seq: int,
    ) -> str:
        """Write a chunk to the local disk spool. Raises SpoolBoundExceeded."""
        async with self._spool_lock:
            if self._spool_bytes + len(data) > self._spool_max_bytes:
                raise SpoolBoundExceeded(
                    f"spool would exceed {self._spool_max_bytes} bytes "
                    f"(current: {self._spool_bytes}, chunk: {len(data)})",
                    tenant_id=tenant_id,
                    recording_id=recording_id,
                    spool_bytes=self._spool_bytes,
                    spool_max=self._spool_max_bytes,
                )

            recording_dir = self._spool_dir / tenant_id / recording_id
            chunk_file = recording_dir / f"chunk_{seq:06d}.opus"

            def _write() -> None:
                recording_dir.mkdir(parents=True, exist_ok=True)
                chunk_file.write_bytes(data)

            await asyncio.to_thread(_write)
            self._spool_bytes += len(data)

        logger.info(
            "chunk_spooled",
            tenant=tenant_id,
            recording=recording_id,
            seq=seq,
            bytes=len(data),
            spool_total=self._spool_bytes,
        )
        return str(chunk_file)

    def _measure_spool_size(self) -> int:
        """Walk the spool directory and sum file sizes."""
        if not self._spool_dir.exists():
            return 0
        total = 0
        for f in self._spool_dir.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total

    @property
    def spool_bytes(self) -> int:
        return self._spool_bytes

    async def drain_spool(self) -> int:
        """Upload all spooled chunks to GCS. Returns number of chunks drained.

        Called on breaker recovery and on startup. Stops if the breaker
        re-opens mid-drain.
        """
        if self._draining:
            logger.info("spool_drain_already_running")
            return 0
        self._draining = True
        try:
            return await self._drain_impl()
        finally:
            self._draining = False

    async def _drain_impl(self) -> int:
        if not self._spool_dir.exists():
            return 0

        drained = 0
        for tenant_dir in sorted(self._spool_dir.iterdir()):
            if not tenant_dir.is_dir():
                continue
            tenant_id = tenant_dir.name

            for recording_dir in sorted(tenant_dir.iterdir()):
                if not recording_dir.is_dir():
                    continue
                recording_id = recording_dir.name

                count = await self._drain_recording(
                    tenant_id, recording_id, recording_dir
                )
                drained += count

                if self._breaker.is_open:
                    logger.info(
                        "spool_drain_interrupted",
                        reason="breaker_reopened",
                        drained_so_far=drained,
                    )
                    return drained

        if drained:
            logger.info("spool_drain_complete", total=drained)
        return drained

    async def _drain_recording(
        self,
        tenant_id: str,
        recording_id: str,
        recording_dir: Path,
    ) -> int:
        """Drain one recording's spooled chunks to GCS."""
        drained = 0
        chunk_files = sorted(recording_dir.glob("chunk_*.opus"))

        for chunk_file in chunk_files:
            try:
                self._breaker.before_call()
            except CircuitBreakerOpen:
                return drained

            seq_str = chunk_file.stem.removeprefix("chunk_")
            try:
                seq = int(seq_str)
            except ValueError:
                logger.warning("spool_bad_filename", path=str(chunk_file))

                def _stat_and_unlink(p: Path) -> int:
                    size = p.stat().st_size
                    p.unlink()
                    return size

                file_size = await asyncio.to_thread(_stat_and_unlink, chunk_file)
                self._spool_bytes = max(0, self._spool_bytes - file_size)
                continue

            blob_path = self._chunk_path(tenant_id, recording_id, seq)
            data = await asyncio.to_thread(chunk_file.read_bytes)
            file_size = len(data)

            try:
                bucket = self._ensure_bucket()
                blob = bucket.blob(blob_path)
                await asyncio.to_thread(
                    blob.upload_from_string, data, content_type="audio/opus"
                )
            except Exception as exc:
                self._breaker.record_failure()
                logger.warning(
                    "spool_drain_upload_failed",
                    tenant=tenant_id,
                    recording=recording_id,
                    seq=seq,
                    error=str(exc),
                )
                return drained

            self._breaker.record_success()
            await asyncio.to_thread(chunk_file.unlink)
            self._spool_bytes = max(0, self._spool_bytes - file_size)
            drained += 1
            logger.info(
                "spool_chunk_drained",
                tenant=tenant_id,
                recording=recording_id,
                seq=seq,
            )

        await asyncio.to_thread(self._cleanup_empty_dir, recording_dir)
        return drained

    @staticmethod
    def _cleanup_empty_dir(directory: Path) -> None:
        """Remove a recording dir and its parent tenant dir if both are empty."""
        if not any(directory.iterdir()):
            directory.rmdir()
            parent = directory.parent
            if not any(parent.iterdir()):
                parent.rmdir()


def register_spool_drain(
    breaker: CircuitBreaker,
    storage: StorageProvider,
) -> None:
    """Wire the GCS breaker's recovery to drain the local spool."""

    async def _safe_drain() -> None:
        try:
            await storage.drain_spool()
        except Exception:
            logger.exception("spool_drain_failed")

    def _on_gcs_recovered(dep: str, old: State, new: State) -> None:
        if new != State.CLOSED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("spool_drain_no_loop")
            return
        loop.create_task(_safe_drain())

    breaker.add_on_state_change(_on_gcs_recovered)


def _is_not_found(exc: Exception) -> bool:
    """Check if an exception indicates a 404 / not-found from GCS."""
    from google.api_core.exceptions import NotFound

    return isinstance(exc, NotFound)
