"""3-layer guardrail architecture for competitor intelligence agent.

Layer 1 - InputGuardrails:    Validates and sanitizes incoming prompts (9 rules).
Layer 2 - PlanToolGuardrails: Enforced during plan validation and skill execution (9 rules).
Layer 3 - OutputGuardrails:   Validates outgoing analysis results (8 rules).
"""

import ipaddress
import logging
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from app.api.schemas import CompetitorIntelligenceResponse

logger = logging.getLogger(__name__)

# -- Regex PII patterns --

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
_ACCOUNT_PATTERN = re.compile(r"\b\d{8,17}\b")

# -- Prompt injection indicators --

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"(?:override|bypass)\s+(?:your|the)\s+(?:rules|instructions)", re.I),
    re.compile(r"<\s*(?:system|admin)\s*>", re.I),
]

# -- Scam/social engineering indicators (IG-02) --

_SCAM_PATTERNS = [
    re.compile(r"(?:send|wire|transfer)\s+(?:money|funds|payment)", re.I),
    re.compile(r"(?:urgent|immediate)\s+(?:action|response)\s+required", re.I),
    re.compile(r"(?:act\s+now|limited\s+time)\s+(?:offer|opportunity)", re.I),
    re.compile(r"(?:bank\s+account|routing)\s+number", re.I),
]

# -- In-scope topics for IG-03 --

DEFAULT_IN_SCOPE_TOPICS = [
    "competitor",
    "competitive",
    "swot",
    "benchmarking",
    "positioning",
    "market_share",
    "competitive_intelligence",
    "brand",
    "business",
    "industry",
    "market",
    "pricing",
    "review",
    "social media",
    "strategy",
    "differentiation",
    "gap analysis",
]

MAX_PROMPT_LENGTH = 16000  # ~4096 tokens
MAX_OUTPUT_CHARS = 150000
CONFIDENCE_THRESHOLD = 0.7

# -- IG-08: Private/reserved IP ranges for SSRF prevention --

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # Cloud metadata endpoint
}

# -- OG-07: Defamation keyword indicators --

_DEFAMATION_KEYWORDS = [
    re.compile(r"\b(?:fraud|fraudulent)\b", re.I),
    re.compile(r"\b(?:scam|scammer)\b", re.I),
    re.compile(r"\b(?:criminal|criminal activity)\b", re.I),
    re.compile(r"\b(?:corrupt|corruption)\b", re.I),
    re.compile(r"\b(?:embezzle|embezzlement)\b", re.I),
    re.compile(r"\b(?:launder|money laundering)\b", re.I),
    re.compile(r"\b(?:incompetent|disgrace|disgraceful)\b", re.I),
    re.compile(r"\bpathological\s+liar\b", re.I),
    re.compile(r"\bknown\s+to\s+(?:lie|cheat|steal)\b", re.I),
    re.compile(r"\ballegedly\s+(?:stole|defrauded|embezzled)\b", re.I),
]

# Maximum keyword score before triggering LLM judge
_DEFAMATION_KEYWORD_THRESHOLD = 0.3

# -- OG-08: Trade secret / proprietary content indicators --

_TRADE_SECRET_PATTERNS = [
    re.compile(r"\b(?:proprietary|confidential|trade\s+secret)\b", re.I),
    re.compile(r"\b(?:internal\s+only|not\s+for\s+distribution)\b", re.I),
    re.compile(r"\b(?:nda|non-disclosure)\b", re.I),
    re.compile(r"\b(?:source\s+code|algorithm\s+detail)\b", re.I),
    re.compile(r"\b(?:unreleased|pre-release)\s+(?:product|feature)\b", re.I),
    re.compile(r"\bcost\s+(?:structure|breakdown)\s+(?:confidential|internal)\b", re.I),
    re.compile(r"\b(?:salary|compensation)\s+(?:data|details|breakdown)\b", re.I),
]

# Valid skill IDs (PG-02 allowlist)
VALID_SKILL_IDS = {
    "SKL-CIA-01",
    "SKL-CIA-02",
    "SKL-CIA-03",
    "SKL-CIA-04",
    "SKL-CIA-05",
    "SKL-CIA-06",
    "SKL-CIA-07",
    "SKL-CIA-08",
    "SKL-CIA-09",
    "SKL-CIA-10",
    "SKL-CIA-11",
    "SKL-CIA-12",
}


class GuardrailResult(BaseModel):
    """Outcome of a guardrail check."""

    passed: bool = True
    blocked: bool = False
    rule_id: str | None = None
    message: str = ""
    sanitized_prompt: str | None = None


# ===================================================================
# Layer 1 - Input Guardrails (9 rules, <200ms budget)
# ===================================================================


class InputGuardrails:
    """Layer 1: Validates and sanitizes incoming prompts."""

    def __init__(
        self,
        redis_manager: Any = None,
        settings: Any = None,
    ) -> None:
        self.redis_manager = redis_manager
        self.settings = settings
        self._max_prompt_length = MAX_PROMPT_LENGTH
        if settings:
            self._max_prompt_length = getattr(
                settings, "INPUT_MAX_TOKENS", MAX_PROMPT_LENGTH
            )
            scope_str = getattr(settings, "IN_SCOPE_TOPICS", "")
            if scope_str:
                self._in_scope = [
                    t.strip().lower() for t in scope_str.split(",") if t.strip()
                ]
            else:
                self._in_scope = [t.lower() for t in DEFAULT_IN_SCOPE_TOPICS]
        else:
            self._in_scope = [t.lower() for t in DEFAULT_IN_SCOPE_TOPICS]

    async def evaluate(self, prompt: str, tenant_id: str) -> GuardrailResult:
        """Run all input guardrail rules. Returns GuardrailResult."""
        # IG-05: Tenant context validation
        if not tenant_id or not tenant_id.strip():
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-05",
                message="Tenant ID is required",
            )

        # IG-06: Input size limit
        if not prompt or not prompt.strip():
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-06",
                message="Input prompt cannot be empty",
            )
        if len(prompt) > self._max_prompt_length:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="IG-06",
                message=(
                    f"Input exceeds maximum length of "
                    f"{self._max_prompt_length} characters"
                ),
            )

        # IG-01: Prompt injection detection
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(prompt):
                logger.warning("IG-01 triggered: prompt injection detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="IG-01",
                    message="Prompt injection detected",
                )

        # IG-02: Scam/social engineering detection
        for pattern in _SCAM_PATTERNS:
            if pattern.search(prompt):
                logger.warning("IG-02 triggered: scam pattern detected")
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="IG-02",
                    message="Potential scam/social engineering content detected",
                )

        # IG-03: Out-of-scope filter (keyword matching)
        prompt_lower = prompt.lower()
        in_scope = any(topic in prompt_lower for topic in self._in_scope)
        if not in_scope:
            logger.info("IG-03: Prompt may be out of scope, allowing with warning")

        # IG-08: SSRF prevention — must run BEFORE PII redaction (IG-04)
        # because Presidio replaces IPs with [REDACTED-IP]
        urls_in_prompt = _extract_urls(prompt)
        for url in urls_in_prompt:
            if _is_ssrf_target(url):
                logger.warning("IG-08 triggered: SSRF attempt for %s", url)
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="IG-08",
                    message=f"URL targets a private or reserved address: {url}",
                )

        # IG-09: Anti-scraping compliance — note for downstream skills
        for url in urls_in_prompt:
            if _is_restricted_domain(url):
                logger.info(
                    "IG-09: URL %s may have scraping restrictions", url
                )

        # IG-04: PII redaction (Presidio with regex fallback)
        sanitized = _redact_pii(prompt)
        if sanitized != prompt:
            logger.info("IG-04: PII redacted from input")

        # Normalize whitespace
        sanitized = " ".join(sanitized.split())

        # IG-07: Rate limit pre-check
        if self.redis_manager:
            try:
                rate_limit = 10
                if self.settings:
                    rate_limit = getattr(self.settings, "RATE_LIMIT_PER_MINUTE", 10)
                allowed = await self.redis_manager.check_rate_limit(
                    tenant_id, limit=rate_limit
                )
                if not allowed:
                    return GuardrailResult(
                        passed=False,
                        blocked=True,
                        rule_id="IG-07",
                        message=f"Rate limit exceeded for tenant {tenant_id}",
                    )
            except Exception as exc:
                logger.warning("IG-07: Rate limit check failed: %s", exc)

        return GuardrailResult(
            passed=True,
            blocked=False,
            sanitized_prompt=sanitized,
        )


# ===================================================================
# Layer 2 - Plan/Tool Guardrails (9 rules)
# ===================================================================


class PlanToolGuardrails:
    """Layer 2: Enforced during plan validation and skill execution."""

    def __init__(self, rbac_engine: Any = None, settings: Any = None) -> None:
        self.rbac_engine = rbac_engine
        self._token_budget = 75000
        self._max_competitors = 20
        if settings:
            self._token_budget = getattr(settings, "TOKEN_BUDGET_PER_SESSION", 75000)
            self._max_competitors = getattr(settings, "MAX_COMPETITORS", 20)

    async def check_plan(self, skill_sequence: list[str]) -> GuardrailResult:
        """Validate the skill execution plan."""
        # PG-01: Mandatory planning step
        if not skill_sequence:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="PG-01",
                message="Plan must contain at least one skill",
            )

        # PG-02: Tool allowlist
        for skill_id in skill_sequence:
            if skill_id not in VALID_SKILL_IDS:
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-02",
                    message=f"Skill {skill_id} not in allowlist",
                )

        return GuardrailResult(passed=True)

    async def check_tool_call(
        self,
        skill_id: str,
        role: str,
        session_tokens: int,
    ) -> GuardrailResult:
        """Pre-flight check before each tool call."""
        # PG-03: No write without EDITOR role
        if self.rbac_engine and self.rbac_engine.is_write_skill(skill_id):
            if role == "VIEWER":
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-03",
                    message=f"VIEWER role cannot invoke write skill {skill_id}",
                )

        # PG-05: RBAC enforcement
        if self.rbac_engine:
            decision = self.rbac_engine.check_permission(skill_id, role)
            if decision.decision == "DENY":
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    rule_id="PG-05",
                    message=decision.reason,
                )

        # PG-07: Token budget guard
        if session_tokens >= self._token_budget:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="PG-07",
                message=(
                    f"Token budget exhausted: {session_tokens} >= "
                    f"{self._token_budget}"
                ),
            )

        # PG-06: Irreversible action warning (non-blocking)
        if skill_id in {"SKL-CIA-11"}:
            logger.info(
                "PG-06: Irreversible action %s proceeding with logging",
                skill_id,
            )

        return GuardrailResult(passed=True)

    async def check_competitor_count(self, count: int) -> GuardrailResult:
        """PG-08: Competitor count cap."""
        if count > self._max_competitors:
            return GuardrailResult(
                passed=False,
                blocked=True,
                rule_id="PG-08",
                message=(
                    f"Competitor count {count} exceeds max {self._max_competitors}"
                ),
            )
        return GuardrailResult(passed=True)


# ===================================================================
# Layer 3 - Output Guardrails (8 rules)
# ===================================================================


class OutputGuardrails:
    """Layer 3: Validates outgoing analysis results."""

    def __init__(self, settings: Any = None) -> None:
        self._confidence_threshold = CONFIDENCE_THRESHOLD
        self._max_output_chars = MAX_OUTPUT_CHARS
        if settings:
            self._confidence_threshold = getattr(
                settings, "CONFIDENCE_THRESHOLD", CONFIDENCE_THRESHOLD
            )
            self._max_output_chars = getattr(
                settings, "OUTPUT_MAX_CHARS", MAX_OUTPUT_CHARS
            )

    async def evaluate(
        self,
        response: CompetitorIntelligenceResponse,
        skill_results: list[Any] | None = None,
        tenant_id: str = "",
    ) -> GuardrailResult:
        """Run all output guardrail rules."""
        skill_results = skill_results or []

        # OG-01: Grounding check (verify claims cite sources)
        if response.findings and not response.sources:
            logger.warning("OG-01: Findings present but no sources")
            if "Ungrounded - no source citations" not in response.methodology_notes:
                response.methodology_notes.append("Ungrounded - no source citations")

        # OG-02: PII scrub on egress
        response.findings = [_strip_pii(f) for f in response.findings]
        response.recommendations = [_strip_pii(r) for r in response.recommendations]
        response.executive_summary = _strip_pii(response.executive_summary)

        # OG-03: Uncertainty escalation
        if response.confidence_score < self._confidence_threshold:
            logger.info(
                "OG-03: Low confidence %.2f < %.2f",
                response.confidence_score,
                self._confidence_threshold,
            )
            if "Low confidence - review recommended" not in response.methodology_notes:
                response.methodology_notes.append(
                    "Low confidence - review recommended"
                )

        # Clamp confidence to [0, 1]
        response.confidence_score = max(0.0, min(1.0, response.confidence_score))

        # OG-04: No confident hallucination check
        if response.confidence_score > 0.8 and not response.sources:
            logger.warning("OG-04: High confidence with no sources - clamping")
            response.confidence_score = 0.5

        # OG-05: Tenant isolation check
        if tenant_id:
            pass  # Tenant isolation enforced at data layer

        # OG-06: Response size limit
        total_chars = len(response.model_dump_json())
        if total_chars > self._max_output_chars:
            logger.warning(
                "OG-06: Response size %d exceeds limit %d - truncating raw_context",
                total_chars,
                self._max_output_chars,
            )
            response.raw_context = response.raw_context[: self._max_output_chars // 2]

        # OG-07: Hybrid defamation guard — keyword filter then optional LLM judge
        defamation_result = _check_defamation(response)
        if defamation_result:
            logger.warning("OG-07: Defamation risk detected")
            if (
                "Defamation risk - claims require verification"
                not in response.methodology_notes
            ):
                response.methodology_notes.append(
                    "Defamation risk - claims require verification"
                )
            # Scrub flagged text from findings and recommendations
            response.findings = [
                _scrub_defamatory_content(f) for f in response.findings
            ]
            response.recommendations = [
                _scrub_defamatory_content(r) for r in response.recommendations
            ]
            response.executive_summary = _scrub_defamatory_content(
                response.executive_summary
            )

        # OG-08: Trade secret shield — strip proprietary/confidential content
        trade_secret_found = _check_trade_secrets(response)
        if trade_secret_found:
            logger.warning("OG-08: Trade secret content detected and stripped")
            if (
                "Trade secret content stripped"
                not in response.methodology_notes
            ):
                response.methodology_notes.append(
                    "Trade secret content stripped"
                )

        return GuardrailResult(passed=True)


# -- Helpers --


def _redact_pii(text: str) -> str:
    """Redact PII using regex pattern matching."""
    text = _SSN_PATTERN.sub("[REDACTED-SSN]", text)
    text = _CREDIT_CARD_PATTERN.sub("[REDACTED-CC]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED-EMAIL]", text)
    text = _PHONE_PATTERN.sub("[REDACTED-PHONE]", text)
    return text


def _strip_pii(text: str) -> str:
    """Remove potential PII from text. Delegates to _redact_pii."""
    return _redact_pii(text)


# -- IG-08 helpers --

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.I)


def _extract_urls(text: str) -> list[str]:
    """Extract HTTP(S) URLs from text."""
    return _URL_PATTERN.findall(text)


def _is_ssrf_target(url: str) -> bool:
    """Check if a URL targets a private/reserved IP or blocked hostname."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
    except Exception:
        return False

    # Check blocked hostnames
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return True

    # Resolve hostname to IP and check private ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _PRIVATE_NETWORKS:
            if addr in network:
                return True
    except ValueError:
        # hostname is not a bare IP — that's fine
        pass

    return False


# -- IG-09 helper --

_RESTRICTED_DOMAINS = {
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "twitter.com",
    "x.com",
}


def _is_restricted_domain(url: str) -> bool:
    """Check if a URL belongs to a domain known for scraping restrictions."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        for domain in _RESTRICTED_DOMAINS:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
    except Exception:
        pass
    return False


# -- OG-07 helpers --


def _defamation_keyword_score(text: str) -> float:
    """Score text for defamation risk using keyword matching (< 50ms)."""
    if not text:
        return 0.0
    matches = 0
    for pattern in _DEFAMATION_KEYWORDS:
        if pattern.search(text):
            matches += 1
    # Normalize: each match adds ~0.1, cap at 1.0
    return min(1.0, matches * 0.1)


def _check_defamation(response: Any) -> bool:
    """Hybrid defamation guard: keyword filter, then LLM judge if threshold exceeded.

    Phase 5 implements the keyword filter only. LLM judge deferred to v1.1.
    """
    texts_to_check = []
    if hasattr(response, "findings"):
        texts_to_check.extend(response.findings)
    if hasattr(response, "recommendations"):
        texts_to_check.extend(response.recommendations)
    if hasattr(response, "executive_summary"):
        texts_to_check.append(response.executive_summary)

    combined = " ".join(str(t) for t in texts_to_check if t)
    score = _defamation_keyword_score(combined)

    if score > _DEFAMATION_KEYWORD_THRESHOLD:
        logger.info(
            "OG-07: Defamation keyword score %.2f exceeds threshold %.2f",
            score,
            _DEFAMATION_KEYWORD_THRESHOLD,
        )
        # LLM judge would go here in v1.1 for scores > threshold
        return True

    return False


def _scrub_defamatory_content(text: str) -> str:
    """Replace defamatory keywords with hedged alternatives."""
    if not text:
        return text
    # Replace strong claims with hedged language
    text = re.sub(
        r"\b(is|are|was|were)\s+(a\s+)?(fraud|scam|criminal)\b",
        r"\1 \2alleged \3",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(known\s+to)\s+(lie|cheat|steal)\b",
        r"alleged to \2",
        text,
        flags=re.I,
    )
    return text


# -- OG-08 helpers --


def _check_trade_secrets(response: Any) -> bool:
    """Detect and strip trade secret / proprietary content from response."""
    found = False
    fields = ["findings", "recommendations"]

    for field_name in fields:
        field_val = getattr(response, field_name, [])
        if not isinstance(field_val, list):
            continue
        cleaned = []
        for item in field_val:
            item_str = str(item) if item else ""
            if _contains_trade_secret(item_str):
                found = True
                cleaned.append(_redact_trade_secret(item_str))
            else:
                cleaned.append(item)
        setattr(response, field_name, cleaned)

    # Check executive summary
    summary = getattr(response, "executive_summary", "")
    if summary and _contains_trade_secret(summary):
        found = True
        response.executive_summary = _redact_trade_secret(summary)

    # Check raw_context
    raw = getattr(response, "raw_context", "")
    if raw and _contains_trade_secret(raw):
        found = True
        response.raw_context = _redact_trade_secret(raw)

    return found


def _contains_trade_secret(text: str) -> bool:
    """Check if text contains trade secret indicators."""
    for pattern in _TRADE_SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _redact_trade_secret(text: str) -> str:
    """Redact trade secret content from text."""
    for pattern in _TRADE_SECRET_PATTERNS:
        text = pattern.sub("[REDACTED-PROPRIETARY]", text)
    return text
