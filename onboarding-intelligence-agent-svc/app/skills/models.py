"""SkillMeta, SkillContext and SkillResult (Design §8).

``SkillMeta`` is the **fleet shape**, matching voc-agent-svc field for field.
A-06's technical note is blunt: "Do not add fields; a diverging dataclass
breaks the shared contract test." Anything OIA-specific belongs in the YAML
declaration or in the skill body, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

DEFAULT_TIMEOUT_MS = 30000
DEFAULT_MAX_RETRIES = 1
ALL_ROLES = ("OWNER", "ADMIN", "EDITOR", "VIEWER")


@dataclass(frozen=True)
class SkillMeta:
    """Declaration metadata for one skill."""

    skill_id: str
    name: str
    description: str = ""
    allowed_roles: tuple[str, ...] = ALL_ROLES
    idempotent: bool = True
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    circuit_breaker_dependency: str = ""


class Origin(StrEnum):
    """Where an invocation came from.

    ``internal_only`` skills (SKL-OIA-13, 15, 16) are SYSTEM in §15. The
    platform has no SYSTEM role, so §8 expresses them as the full role set
    plus a marker — which means RBAC alone would let any role invoke them.
    The origin is what actually gates them: only the service's own pipelines
    may call one, never a caller who arrived over HTTP or a socket.
    """

    #: Raised by this service's own executors and live-session loop.
    INTERNAL = "INTERNAL"
    #: Arrived from outside — an API request, a WebSocket frame.
    EXTERNAL = "EXTERNAL"


@dataclass
class TenantContext:
    """Who is calling, resolved from the verified JWT — never from a body."""

    tenant_id: str
    user_id: str | None = None
    role: str = "VIEWER"
    session_id: str | None = None


@dataclass
class SkillContext:
    """The fleet-standard five inputs (§8), plus who is asking.

    Every skill takes the same five fields; the per-skill meaning of
    ``input_context`` is documented in each declaration's description.
    """

    input_prompt: str
    tenant_context: TenantContext
    input_context: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    previous_outputs: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    #: Defaults to EXTERNAL so a caller who forgets to say gets the *stricter*
    #: treatment rather than accidental access to an internal-only skill.
    origin: Origin = Origin.EXTERNAL


@dataclass
class SkillResult:
    """What a non-streaming skill returns."""

    skill_id: str
    output: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    duration_ms: int = 0
    prompt_version: str | None = None
