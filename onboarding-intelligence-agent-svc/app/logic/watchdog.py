"""Stuck-session watchdog (M-04, Design §20 AC-3).

Background asyncio task that scans Redis for LIVE sessions whose heartbeat has
gone stale (older than ``WATCHDOG_TIMEOUT_S``). When one is found, the watchdog
asks Django to finalize the session (MEETING_LIVE -> GATHERED), clears the
heartbeat to prevent re-triggering, and emits EVT-009.

Only LIVE sessions write heartbeats (via ``_hold()``). PREP and PROCESS modes
never call ``write_heartbeat()``, so sessions without the field are silently
skipped — not stuck, just a different mode.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TYPE_CHECKING

from app.core.logging import get_logger
from app.events.catalog import EventType

if TYPE_CHECKING:
    from app.events.emitter import EventEmitter
    from app.services.backend_client import BackendClient

logger = get_logger(__name__)

KEY_PREFIX = "oia:v1:"
SESSION_PATTERN = f"{KEY_PREFIX}*:session:*"


def _parse_session_key(key: str) -> tuple[str, str] | None:
    """Extract (tenant_id, session_id) from a session hash key.

    Expected format: ``oia:v1:{tenant_id}:session:{session_id}``
    Skips summary keys (``…:session:{id}:summary``).
    """
    if ":summary" in key:
        return None
    parts = key.split(":")
    if len(parts) != 5 or parts[2] == "" or parts[4] == "":
        return None
    return parts[2], parts[4]


async def _scan_and_close(
    redis: Any,
    backend: "BackendClient",
    events: "EventEmitter",
    timeout_s: float,
) -> int:
    """One scan pass. Returns the number of sessions closed."""
    closed = 0
    cursor: int = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=SESSION_PATTERN, count=100)
        for raw_key in keys:
            key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            parsed = _parse_session_key(key)
            if parsed is None:
                continue
            tenant_id, session_id = parsed

            hb_raw = await redis.hget(key, "last_heartbeat")
            if hb_raw is None:
                continue

            hb_str = hb_raw.decode() if isinstance(hb_raw, bytes) else hb_raw
            try:
                last_hb = float(hb_str)
            except (ValueError, TypeError):
                continue

            age = time.time() - last_hb
            if age < timeout_s:
                continue

            await _close_stuck(redis, backend, events, key, tenant_id, session_id, age)
            closed += 1

        if cursor == 0:
            break
    return closed


async def _close_stuck(
    redis: Any,
    backend: "BackendClient",
    events: "EventEmitter",
    key: str,
    tenant_id: str,
    session_id: str,
    age_s: float,
) -> None:
    logger.warning(
        "watchdog_stuck_session",
        session_id=session_id,
        tenant_id=tenant_id,
        heartbeat_age_s=round(age_s, 1),
    )

    await backend.finalize_stuck_session(tenant_id=tenant_id, session_id=session_id)

    await redis.hdel(key, "last_heartbeat")

    try:
        await events.emit(
            EventType.AGENT_FAILED,
            tenant_id=tenant_id,
            correlation_id=session_id,
            session_id=session_id,
            outcome="FAILURE",
            payload={
                "reason": "stuck_session_watchdog",
                "heartbeat_age_s": round(age_s, 1),
            },
        )
    except Exception:
        logger.warning("watchdog_event_emit_failed", session_id=session_id)


async def watchdog_loop(
    redis: Any,
    backend: "BackendClient",
    events: "EventEmitter",
    interval_s: float = 60,
    timeout_s: float = 300,
) -> None:
    """Run forever, scanning for stuck sessions every ``interval_s``."""
    logger.info(
        "watchdog_started",
        interval_s=interval_s,
        timeout_s=timeout_s,
    )
    while True:
        try:
            closed = await _scan_and_close(redis, backend, events, timeout_s)
            if closed:
                logger.info("watchdog_sweep_done", closed=closed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("watchdog_sweep_error")

        await asyncio.sleep(interval_s)
