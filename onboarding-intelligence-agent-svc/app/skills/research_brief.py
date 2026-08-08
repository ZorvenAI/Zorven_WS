"""The BusinessResearchBrief — SKL-OIA-01's output shape.

Design §8.1 ("BusinessResearchBrief {facts[], competitors_seen[],
digital_presence{}, open_unknowns[]}") · story C-02.

The field names come from the design string above rather than being tidied,
because SKL-OIA-02 consumes this directly: C-03's declaration says
"input_context carries the BusinessResearchBrief from SKL-OIA-01".

**Unknowns are the point.** The card is explicit: "Unknowns are not a
consolation prize — they are the highest-value output of this skill, because
SKL-OIA-02 turns them directly into questions." A brief with many unknowns and
few facts is a *good* brief for a business with a thin web presence; the
failure mode is a brief that invents facts to look complete.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Fact(BaseModel):
    """One established fact, and where it came from.

    ``source_url`` is required and non-empty. AC-1: "every asserted fact
    carries a source URL; a fact the agent cannot source is placed under
    unknowns rather than stated." Making it optional here would push that
    guarantee into every consumer.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    source_url: str = Field(min_length=1)

    @field_validator("source_url")
    @classmethod
    def _must_look_like_a_url(cls, v: str) -> str:
        # Deliberately shallow: the job is to reject "the company website" and
        # "unknown" being passed off as citations, not to validate reachability.
        # A dead link is still a checkable claim; a non-link is not.
        if not v.startswith(("http://", "https://")):
            raise ValueError("a source must be an http(s) URL")
        return v


class DigitalPresence(BaseModel):
    """What the business looks like online.

    Every field is optional because absence is meaningful here — no LinkedIn
    is a real finding about a business, and SKL-OIA-02 can ask about it.
    """

    model_config = ConfigDict(extra="forbid")

    website: str | None = None
    social_profiles: list[str] = Field(default_factory=list)
    notes: str = ""


class BusinessResearchBrief(BaseModel):
    """What SKL-OIA-01 returns (§8.1)."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    facts: list[Fact] = Field(default_factory=list)
    competitors_seen: list[str] = Field(default_factory=list)
    digital_presence: DigitalPresence = Field(default_factory=DigitalPresence)
    open_unknowns: list[str] = Field(default_factory=list)

    #: AC-3. True when research could not run — the breaker was open, the key
    #: was absent, or the search failed. The operator is told, because the
    #: questions that follow are less grounded than usual.
    degraded: bool = False
    degraded_reason: str = ""

    sources: list[str] = Field(
        default_factory=list,
        description="Every URL consulted, including ones that yielded nothing",
    )

    @property
    def is_grounded(self) -> bool:
        """True when every fact carries a source.

        Always true by construction — Fact requires one — but stated so the
        OG-01 rule has something to assert against rather than re-deriving the
        invariant.
        """
        return all(f.source_url for f in self.facts)

    def summary_line(self) -> str:
        """One line for the chat turn.

        A degraded brief says so first. Burying that after the counts would
        let an operator skim past the reason their questions are thinner.
        """
        if self.degraded:
            return (
                f"Research unavailable for {self.company_name} "
                f"({self.degraded_reason}) — "
                f"{len(self.open_unknowns)} open questions to cover."
            )
        return (
            f"{len(self.facts)} sourced facts about {self.company_name}, "
            f"{len(self.competitors_seen)} likely competitors, "
            f"{len(self.open_unknowns)} open unknowns."
        )
