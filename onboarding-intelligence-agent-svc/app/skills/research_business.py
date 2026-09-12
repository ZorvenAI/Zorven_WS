"""SKL-OIA-01 — Research the prospective brand's business ahead of the meeting.

Design §8.1 · implemented by story C-02.

The shape of the work: search the web for the business, hand what came back to
the model, and ask it to separate *what the sources establish* from *what
remains unknown*. The model never researches on its own — it only organises
retrieved text — because a model asked to "research" a small business will
produce fluent, plausible, unsourced claims, which is the failure AC-1 exists
to prevent.

Degradation (AC-3) is not an error path bolted on. Every failure — breaker
open, no API key, search failed — produces a *real brief* built from the
operator's own hints, flagged ``degraded: true`` with the reason. The operator
still gets questions; they are told the questions are less grounded.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.providers.tavily import SearchResult, TavilyProvider, TavilyUnavailable
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.research_brief import BusinessResearchBrief, DigitalPresence, Fact

logger = get_logger(__name__)

SKILL_ID = "SKL-OIA-01"

#: Asked for explicitly, because the card is emphatic that unknowns are the
#: highest-value output — SKL-OIA-02 turns them straight into questions. A
#: model left to its own devices optimises for looking complete.
PROMPT = """\
You are preparing for a brand onboarding meeting with a business.

Operator-provided hints:
- Company name: {company_name}
- Website: {website}
- Industry: {industry}
- Notes from the operator: {notes}

Web search results (the ONLY source material you may assert facts from):
{sources}

Produce a JSON object with exactly these keys:
  "facts": a list of {{"statement": str, "source_url": str}}. Every statement
    MUST be supported by one of the search results above, and source_url MUST
    be that result's URL, copied exactly. If you cannot point to a result, do
    not state it as a fact.
  "competitors_seen": a list of competitor names appearing in the results.
  "digital_presence": {{"website": str or null, "social_profiles": [str],
    "notes": str}}.
  "open_unknowns": a list of specific things you could NOT establish and that
    an interviewer should ask about. This is the most valuable part of your
    output. Be concrete — "what is their average order value" beats "more
    financial detail". Aim for at least five when the sources are thin.

Return ONLY the JSON object, no prose and no code fence.
"""


def normalise_company_name(name: str) -> str:
    """A stable cache key component.

    The card asks for caching by ``(tenant, normalised business name)``.
    Operators retype the name across turns while tuning question count, and
    "Kalyani Roasters", "kalyani roasters" and "Kalyani  Roasters Pvt. Ltd."
    should not each cost a fresh round of paid search.
    """
    lowered = name.strip().lower()
    lowered = re.sub(r"[.,]", "", lowered)
    # Common suffixes carry no identity and vary by how the operator typed it.
    lowered = re.sub(
        r"\b(pvt|private|ltd|limited|llp|inc|incorporated|co|corp|llc)\b", " ", lowered
    )
    return re.sub(r"\s+", " ", lowered).strip()


class ResearchBusiness(BaseSkill):
    """Research the prospective brand's business ahead of the onboarding meeting."""

    def __init__(
        self,
        meta: Any,
        *,
        tavily: TavilyProvider | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        super().__init__(meta)
        self._tavily = tavily
        self._llm = llm

    async def run(self, context: SkillContext) -> SkillResult:
        hints = context.input_context or {}
        company_name = str(hints.get("company_name") or "").strip()

        if not company_name:
            # Without a name there is nothing to search for and nothing to
            # cache against. Degrading is more useful than raising: the
            # operator gets a brief that says what it needs from them.
            brief = self._degraded(
                company_name="(unnamed business)",
                reason="no company name was provided",
                hints=hints,
            )
            return SkillResult(skill_id=SKILL_ID, output=brief.model_dump())

        try:
            results = await self._search(company_name, hints)
        except TavilyUnavailable as exc:
            logger.warning("research_degraded", company=company_name, reason=exc.reason)
            brief = self._degraded(company_name, exc.reason, hints)
            return SkillResult(skill_id=SKILL_ID, output=brief.model_dump())

        try:
            brief = await self._synthesise(company_name, hints, results)
        except LLMUnavailable as exc:
            logger.warning(
                "research_synthesis_degraded", company=company_name, reason=exc.reason
            )
            brief = self._degraded(company_name, exc.reason, hints, sources=results)
            return SkillResult(skill_id=SKILL_ID, output=brief.model_dump())

        return SkillResult(skill_id=SKILL_ID, output=brief.model_dump())

    # ── The two external calls ───────────────────────────────────────

    async def _search(
        self, company_name: str, hints: dict[str, Any]
    ) -> list[SearchResult]:
        if self._tavily is None:
            raise TavilyUnavailable("web research is not configured")

        website = str(hints.get("website") or "").strip()
        industry = str(hints.get("industry") or "").strip()
        query = " ".join(part for part in (company_name, industry, website) if part)
        return await self._tavily.search(query)

    async def _synthesise(
        self,
        company_name: str,
        hints: dict[str, Any],
        results: list[SearchResult],
    ) -> BusinessResearchBrief:
        if self._llm is None:
            raise LLMUnavailable("no LLM is configured")

        prompt = PROMPT.format(
            company_name=company_name,
            website=hints.get("website") or "(not provided)",
            industry=hints.get("industry") or "(not provided)",
            notes=hints.get("operator_notes") or "(none)",
            sources=self._render(results),
        )
        raw = await self._llm.generate(prompt)
        return self._parse(raw, company_name, results)

    @staticmethod
    def _render(results: list[SearchResult]) -> str:
        if not results:
            return "(no search results — you may not assert any facts)"
        return "\n".join(
            f"[{i}] {r.title}\n    URL: {r.url}\n    {r.snippet}"
            for i, r in enumerate(results, 1)
        )

    # ── Turning a completion into a brief ────────────────────────────

    def _parse(
        self, raw: str, company_name: str, results: list[SearchResult]
    ) -> BusinessResearchBrief:
        """Build a brief from the model's JSON, keeping only sourced facts.

        A fact whose ``source_url`` is not one of the URLs we actually
        retrieved is dropped to unknowns here, before OG-01 sees it. The model
        inventing a plausible citation is a real failure mode and it defeats a
        grounding rule that only checks the field is present and URL-shaped.
        """
        payload = self._json_object(raw)
        known_urls = {r.url for r in results}

        facts: list[Fact] = []
        unknowns: list[str] = [
            str(u).strip() for u in payload.get("open_unknowns", []) if str(u).strip()
        ]

        for item in payload.get("facts", []):
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            url = str(item.get("source_url") or "").strip()
            if not statement:
                continue
            if url not in known_urls:
                unknowns.append(f"Unverified: {statement}")
                continue
            facts.append(Fact(statement=statement, source_url=url))

        digital = self._digital_presence(payload.get("digital_presence"))

        return BusinessResearchBrief(
            company_name=company_name,
            facts=facts,
            competitors_seen=[
                str(c).strip()
                for c in payload.get("competitors_seen", [])
                if str(c).strip()
            ],
            digital_presence=digital,
            open_unknowns=unknowns,
            sources=[r.url for r in results],
        )

    @staticmethod
    def _digital_presence(presence: Any) -> DigitalPresence:
        """Read the digital-presence block, whatever the model actually sent.

        Two distinct failures, both found by review:

        A non-object — a list, a bare string, a number — made ``.get()`` raise
        ``AttributeError`` and took down the whole turn, which is precisely
        what the degraded path exists to avoid.

        A *string* ``social_profiles`` was quieter and worse: iterating it
        yields single characters, so ``"twitter"`` became eight one-letter
        "profiles" and was carried into the brief as if it were data. A crash
        gets noticed; this would not have.
        """
        if not isinstance(presence, dict):
            return DigitalPresence()

        website = presence.get("website")
        profiles = presence.get("social_profiles")

        return DigitalPresence(
            website=website if isinstance(website, str) and website.strip() else None,
            social_profiles=(
                [str(p).strip() for p in profiles if str(p).strip()]
                if isinstance(profiles, list)
                else []
            ),
            notes=str(presence.get("notes") or ""),
        )

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        """Extract the JSON object from a completion.

        Models wrap JSON in code fences and prose despite instructions, so the
        first ``{`` to the last ``}`` is taken rather than trusting the whole
        string. An unparseable completion yields an empty object, which
        degrades to a brief of pure unknowns rather than raising — the
        operator is better served by questions than by an error.
        """
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            logger.warning("research_completion_had_no_json_object")
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
            logger.warning("research_completion_was_not_valid_json")
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ── AC-3 ─────────────────────────────────────────────────────────

    @staticmethod
    def _degraded(
        company_name: str,
        reason: str,
        hints: dict[str, Any],
        sources: list[SearchResult] | None = None,
    ) -> BusinessResearchBrief:
        """A brief built from the operator's own words, flagged as thin.

        The unknowns here are deliberately generic — with no research there is
        nothing specific to be curious about, and pretending otherwise would
        misrepresent what the agent knows. They still give SKL-OIA-02 the
        skeleton of a questionnaire, which is the point of degrading rather
        than failing.
        """
        notes = str(hints.get("operator_notes") or "").strip()
        website = str(hints.get("website") or "").strip() or None

        return BusinessResearchBrief(
            company_name=company_name,
            facts=[],
            competitors_seen=[],
            digital_presence=DigitalPresence(
                website=website,
                notes=notes,
            ),
            open_unknowns=[
                "What does the business actually sell, and to whom?",
                "Who are its main competitors, and how does it differ from them?",
                "What is its current marketing and digital presence?",
                "Who is the target customer, in the operator's own words?",
                "What does the business believe makes it distinctive?",
            ],
            degraded=True,
            degraded_reason=reason,
            sources=[r.url for r in (sources or [])],
        )
