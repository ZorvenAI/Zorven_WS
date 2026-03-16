"""
Layered prompt caching for chat sessions.

Builds a 3-layer prompt (static instructions, tool definitions, company knowledge),
hashes the prefix, and caches the snapshot in Redis per tenant+session.

Redis keys (all in Django's default cache / DB 0):
  ba:prompt_cache:{tenant_id}:{session_id}:snapshot  — 24h TTL
  ba:prompt_cache:metrics:{tenant_id}:hits            — 24h TTL
  ba:prompt_cache:metrics:{tenant_id}:misses          — 24h TTL
  ba:prompt_cache:metrics:global:hits                 — 24h TTL
  ba:prompt_cache:metrics:global:misses               — 24h TTL
"""

import hashlib
import logging
from typing import Any, Dict, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

SNAPSHOT_TTL = 86400  # 24 hours
METRICS_TTL = 86400  # 24 hours

# Fixed tool set — locked at session start (Rule 3)
CHAT_TOOLS = [
    {
        "name": "classify_intent",
        "description": "Classify user message as pipeline, rag, or conversation",
    },
    {
        "name": "search_documents",
        "description": "Search uploaded documents in the RAG knowledge base",
    },
    {
        "name": "analyze_brand",
        "description": (
            "Run a full brand analysis pipeline " "(discovery, valuation, content)"
        ),
    },
    {
        "name": "write_blog",
        "description": "Author an SEO/AEO/GEO optimized blog post",
    },
    {
        "name": "schedule_post",
        "description": "Schedule social media posts to LinkedIn, Twitter, etc.",
    },
    {
        "name": "get_brand_info",
        "description": "Retrieve company profile and brand strategy data",
    },
]

# Same field_labels map used in services.py _build_chat_system_prompt
_FIELD_LABELS = {
    "name": "Company",
    "description": "Description",
    "industry": "Industry",
    "website": "Website",
    "target_audience": "Target Audience",
    "core_problem": "Core Problem",
    "demographics": "Demographics",
    "psychographics": "Psychographics",
    "pain_points": "Pain Points",
    "desired_outcomes": "Desired Outcomes",
    "brand_voice": "Brand Voice",
    "vision_statement": "Vision Statement",
    "mission_statement": "Mission Statement",
    "values": "Values",
    "positioning_statement": "Positioning Statement",
    "tagline": "Tagline",
    "value_proposition": "Value Proposition",
    "elevator_pitch": "Elevator Pitch",
    "color_palette_desc": "Color Palette",
    "font_recommendations": "Font Recommendations",
    "messaging_guide": "Messaging Guide",
}


def build_layer_1() -> str:
    """Layer 1: Static system instructions (never changes mid-session)."""
    return (
        "You are Zorven AI, an expert brand strategy assistant.\n"
        "You help users build, evaluate, and improve their brands.\n"
        "Provide thoughtful, actionable advice using markdown formatting.\n"
        "Use headings, bullet points, and bold text for clarity."
    )


def build_layer_2() -> str:
    """Layer 2: Tool definitions formatted as text (fixed at session start)."""
    lines = ["Available tools:"]
    for tool in CHAT_TOOLS:
        lines.append(f"- {tool['name']}: {tool['description']}")
    return "\n".join(lines)


def build_layer_3(company_data: Dict[str, Any]) -> str:
    """Layer 3: Company knowledge base from profile fields."""
    parts = []
    for field, label in _FIELD_LABELS.items():
        val = company_data.get(field)
        if val:
            parts.append(f"{label}: {val}")
    return "\n".join(parts) if parts else ""


def compute_prefix_hash(layer_1: str, layer_2: str, layer_3: str) -> str:
    """SHA-256 hash of layers 1-3 (first 16 chars)."""
    combined = f"{layer_1}\n{layer_2}\n{layer_3}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def get_or_create_prompt_snapshot(
    tenant_id: int,
    session_id: str,
    company_data: Dict[str, Any],
) -> Dict[str, str]:
    """Return cached prompt snapshot or build a fresh one.

    Fail-open on Redis errors — always returns a valid snapshot.
    """
    cache_key = f"ba:prompt_cache:{tenant_id}:{session_id}:snapshot"

    # Try cache first
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            _record_hit(tenant_id)
            return cached
    except Exception:
        logger.warning("Redis read failed for prompt cache, building fresh")

    # Cache miss — build snapshot
    _record_miss(tenant_id, "cold_start")

    layer_1 = build_layer_1()
    layer_2 = build_layer_2()
    layer_3 = build_layer_3(company_data)
    prefix_hash = compute_prefix_hash(layer_1, layer_2, layer_3)

    snapshot = {
        "layer_1": layer_1,
        "layer_2": layer_2,
        "layer_3": layer_3,
        "prefix_hash": prefix_hash,
    }

    # Store in cache (fail-open)
    try:
        cache.set(cache_key, snapshot, timeout=SNAPSHOT_TTL)
    except Exception:
        logger.warning("Redis write failed for prompt cache snapshot")

    return snapshot


def build_system_prompt_from_snapshot(snapshot: Dict[str, str]) -> str:
    """Assemble the full system prompt from a cached snapshot."""
    parts = [snapshot["layer_1"], snapshot["layer_2"]]
    if snapshot.get("layer_3"):
        parts.append(snapshot["layer_3"])
    return "\n\n".join(parts)


def get_cache_metrics(
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Read hit/miss counters from Redis.

    If tenant_id is provided, returns per-tenant metrics.
    Always includes global metrics.
    """
    result: Dict[str, Any] = {}

    try:
        global_hits = cache.get("ba:prompt_cache:metrics:global:hits") or 0
        global_misses = cache.get("ba:prompt_cache:metrics:global:misses") or 0
        total = global_hits + global_misses
        hit_rate = (global_hits / total * 100) if total > 0 else 0.0

        if hit_rate >= 80:
            health = "healthy"
        elif hit_rate >= 50:
            health = "warning"
        else:
            health = "critical"

        result["global"] = {
            "hits": global_hits,
            "misses": global_misses,
            "total": total,
            "hit_rate_percent": round(hit_rate, 1),
            "health": health,
        }

        if tenant_id is not None:
            t_hits = cache.get(f"ba:prompt_cache:metrics:{tenant_id}:hits") or 0
            t_misses = cache.get(f"ba:prompt_cache:metrics:{tenant_id}:misses") or 0
            t_total = t_hits + t_misses
            t_rate = (t_hits / t_total * 100) if t_total > 0 else 0.0
            result["tenant"] = {
                "hits": t_hits,
                "misses": t_misses,
                "total": t_total,
                "hit_rate_percent": round(t_rate, 1),
            }
    except Exception:
        logger.warning("Failed to read prompt cache metrics from Redis")
        result["global"] = {
            "hits": 0,
            "misses": 0,
            "total": 0,
            "hit_rate_percent": 0.0,
            "health": "critical",
        }

    return result


def _record_hit(tenant_id: int) -> None:
    """Increment hit counters (fail-open)."""
    try:
        _safe_incr(f"ba:prompt_cache:metrics:{tenant_id}:hits")
        _safe_incr("ba:prompt_cache:metrics:global:hits")
    except Exception:
        pass


def _record_miss(tenant_id: int, reason: str = "") -> None:
    """Increment miss counters (fail-open)."""
    try:
        _safe_incr(f"ba:prompt_cache:metrics:{tenant_id}:misses")
        _safe_incr("ba:prompt_cache:metrics:global:misses")
    except Exception:
        pass
    if reason:
        logger.debug("Prompt cache miss for tenant %s: %s", tenant_id, reason)


def _safe_incr(key: str) -> None:
    """Increment a Redis counter, initializing to 1 if absent."""
    try:
        cache.incr(key)
    except ValueError:
        # Key does not exist yet
        cache.set(key, 1, timeout=METRICS_TTL)
