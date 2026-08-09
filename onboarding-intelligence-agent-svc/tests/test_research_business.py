"""C-02 · SKL-OIA-01, the research brief, and its degraded path.

No mocks. The skill is driven through real providers pointed at local HTTP
servers, so a real ``AsyncTavilyClient`` and a real breaker are in the path.
The LLM is the one place a local server will not do — Gemini's SDK is not
base-URL-configurable the way Tavily's is — so those cases use a tiny local
stand-in object implementing the one method the provider calls. That is a
seam, not a mock: nothing is patched, and the provider's own breaker,
error-handling and text-extraction all still run.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.providers.llm import LLMProvider
from app.providers.tavily import TavilyProvider
from app.skills.models import SkillContext, SkillMeta, TenantContext
from app.skills.research_brief import BusinessResearchBrief
from app.skills.research_business import ResearchBusiness, normalise_company_name

REAL_URL = "https://kalyani.example/about"


def meta() -> SkillMeta:
    return SkillMeta(
        skill_id="SKL-OIA-01",
        name="research_business",
        description="research",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
    )


def context(**overrides) -> SkillContext:
    input_context = {
        "company_name": "Kalyani Roasters",
        "website": "https://kalyani.example",
        "industry": "speciality coffee",
        "operator_notes": "Family run, wants to sell online.",
    }
    input_context.update(overrides.pop("input_context", {}))
    return SkillContext(
        input_prompt="prep the onboarding call",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
        **overrides,
    )


def brk(name: str, **overrides) -> CircuitBreaker:
    base = dict(
        name=name,
        failure_threshold=3,
        window_seconds=60,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="SKIP_RESEARCH" if name == "tavily" else "MANUAL_CHECKBOXES",
        user_message="unavailable",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


class StubModel:
    """The one method LLMProvider calls on a Gemini model.

    Not a mock framework and not a patch — a real object satisfying a
    one-method interface, so the provider's breaker, exception handling and
    empty-completion check all still execute for real.
    """

    def __init__(self, text: str = "", raises: Exception | None = None) -> None:
        self._text = text
        self._raises = raises
        self.prompts: list[str] = []

    async def generate_content_async(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self._raises:
            raise self._raises

        class Response:
            text = self._text

        return Response()


@pytest.fixture
def tavily_server():
    state = {"status": 200, "body": {"results": []}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            payload = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def tavily_for(state, breaker=None) -> TavilyProvider:
    from tavily import AsyncTavilyClient

    return TavilyProvider(
        "k",
        breaker=breaker or brk("tavily"),
        client=AsyncTavilyClient(api_key="k", api_base_url=state["url"]),
    )


def llm_for(model) -> LLMProvider:
    return LLMProvider("k", breaker=brk("llm"), client=model)


def one_result(state):
    state["body"] = {
        "results": [
            {
                "title": "Kalyani Roasters — About",
                "url": REAL_URL,
                "content": "A speciality coffee roaster in Pune, founded 2016.",
            }
        ]
    }


# ── AC-1 · a structured brief with sources ───────────────────────────


@pytest.mark.integration
async def test_a_sourced_fact_survives(tavily_server):
    one_result(tavily_server)
    model = StubModel(
        json.dumps(
            {
                "facts": [
                    {"statement": "Founded in 2016.", "source_url": REAL_URL},
                ],
                "competitors_seen": ["Blue Tokai"],
                "digital_presence": {"website": "https://kalyani.example"},
                "open_unknowns": ["What is their average order value?"],
            }
        )
    )
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server), llm=llm_for(model)
    )

    result = await skill.run(context())
    brief = BusinessResearchBrief.model_validate(result.output)

    assert [f.statement for f in brief.facts] == ["Founded in 2016."]
    assert brief.facts[0].source_url == REAL_URL
    assert brief.competitors_seen == ["Blue Tokai"]
    assert brief.open_unknowns == ["What is their average order value?"]
    assert brief.degraded is False


@pytest.mark.integration
async def test_a_fact_citing_a_url_we_never_retrieved_becomes_an_unknown(tavily_server):
    """The failure mode a URL-shape check misses.

    A model that invents a plausible citation passes any rule that only asks
    "is source_url present and http(s)". The only defence is checking it
    against what search actually returned.
    """
    one_result(tavily_server)
    model = StubModel(
        json.dumps(
            {
                "facts": [
                    {"statement": "Founded in 2016.", "source_url": REAL_URL},
                    {
                        "statement": "Revenue is 40 crore.",
                        "source_url": "https://invented.example/financials",
                    },
                ],
                "open_unknowns": [],
            }
        )
    )
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server), llm=llm_for(model)
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert [f.statement for f in brief.facts] == ["Founded in 2016."]
    assert brief.open_unknowns == ["Unverified: Revenue is 40 crore."]


@pytest.mark.integration
async def test_the_prompt_carries_the_retrieved_sources(tavily_server):
    """The model organises retrieved text; it does not research on its own.
    If the sources never reach the prompt, every fact it produces is invented.
    """
    one_result(tavily_server)
    model = StubModel(json.dumps({"facts": [], "open_unknowns": []}))
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server), llm=llm_for(model)
    )

    await skill.run(context())

    assert REAL_URL in model.prompts[0]
    assert "Kalyani Roasters" in model.prompts[0]


@pytest.mark.integration
async def test_an_unparseable_completion_yields_unknowns_not_an_error(tavily_server):
    """The operator is better served by questions than by an error."""
    one_result(tavily_server)
    skill = ResearchBusiness(
        meta(),
        tavily=tavily_for(tavily_server),
        llm=llm_for(StubModel("I'm afraid I can't do that.")),
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert brief.facts == []
    assert brief.degraded is False, "a bad completion is not a dependency outage"


@pytest.mark.integration
async def test_a_fenced_json_completion_is_still_read(tavily_server):
    """Models add code fences despite instructions."""
    one_result(tavily_server)
    fenced = (
        "```json\n"
        + json.dumps(
            {"facts": [{"statement": "Founded 2016.", "source_url": REAL_URL}]}
        )
        + "\n```"
    )
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server), llm=llm_for(StubModel(fenced))
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert len(brief.facts) == 1


# ── AC-3 · degradation is flagged, never silent ──────────────────────


@pytest.mark.integration
async def test_an_open_tavily_breaker_produces_a_degraded_brief(tavily_server):
    """The card's named case: test_tavily_open_produces_degraded_brief."""
    breaker = brk("tavily", failure_threshold=1)
    breaker.record_failure()
    skill = ResearchBusiness(
        meta(),
        tavily=tavily_for(tavily_server, breaker),
        llm=llm_for(StubModel("{}")),
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert brief.degraded is True
    assert brief.degraded_reason
    assert brief.facts == [], "a degraded brief must assert nothing"
    assert len(brief.open_unknowns) >= 5, "the operator still needs questions"


@pytest.mark.integration
async def test_a_degraded_brief_keeps_the_operators_own_information(tavily_server):
    """AC-3: "a brief from the operator-provided information only"."""
    breaker = brk("tavily", failure_threshold=1)
    breaker.record_failure()
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server, breaker), llm=llm_for(StubModel("{}"))
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert brief.company_name == "Kalyani Roasters"
    assert brief.digital_presence.website == "https://kalyani.example"
    assert "Family run" in brief.digital_presence.notes


@pytest.mark.unit
async def test_no_providers_at_all_still_produces_a_brief():
    """A skill resolved by the registry with no providers wired — the state
    of a deployment with no Tavily key. It must degrade, not raise."""
    brief = BusinessResearchBrief.model_validate(
        (await ResearchBusiness(meta()).run(context())).output
    )

    assert brief.degraded is True
    assert brief.open_unknowns


@pytest.mark.unit
async def test_a_missing_company_name_degrades_rather_than_searching():
    skill = ResearchBusiness(meta())

    brief = BusinessResearchBrief.model_validate(
        (await skill.run(context(input_context={"company_name": "  "}))).output
    )

    assert brief.degraded is True
    assert "no company name" in brief.degraded_reason


@pytest.mark.integration
async def test_the_summary_line_leads_with_the_degradation(tavily_server):
    """An operator skimming must not miss why their questions are thin."""
    breaker = brk("tavily", failure_threshold=1)
    breaker.record_failure()
    skill = ResearchBusiness(
        meta(), tavily=tavily_for(tavily_server, breaker), llm=llm_for(StubModel("{}"))
    )

    brief = BusinessResearchBrief.model_validate((await skill.run(context())).output)

    assert brief.summary_line().startswith("Research unavailable")


# ── Cache key normalisation ──────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "written",
    [
        "Kalyani Roasters",
        "kalyani roasters",
        "  Kalyani   Roasters  ",
        "Kalyani Roasters Pvt. Ltd.",
        "KALYANI ROASTERS PRIVATE LIMITED",
    ],
)
def test_the_same_business_normalises_to_one_key(written):
    """Each variant otherwise costs a fresh round of paid search."""
    assert normalise_company_name(written) == "kalyani roasters"


@pytest.mark.unit
def test_different_businesses_do_not_collide():
    assert normalise_company_name("Kalyani Roasters") != normalise_company_name(
        "Kalyani Textiles"
    )


# ── Property: nothing is asserted without a source ───────────────────


@pytest.mark.property
@hyp_settings(max_examples=60, deadline=None)
@given(
    statements=st.lists(st.text(min_size=1, max_size=40), max_size=6),
    urls=st.lists(
        st.sampled_from(
            [REAL_URL, "https://other.example", "", "not-a-url", "ftp://x"]
        ),
        max_size=6,
    ),
)
def test_every_surviving_fact_is_sourced_and_nothing_is_silently_lost(statements, urls):
    """Two invariants over arbitrary model output.

    Conservation is the one worth encoding: a claim is either kept with a real
    source or demoted to an unknown, never dropped on the floor. A grounding
    rule that silently deleted unsourced claims would satisfy "every fact is
    sourced" perfectly while destroying the signal SKL-OIA-02 depends on.
    """
    pairs = list(zip(statements, urls))
    raw = json.dumps({"facts": [{"statement": s, "source_url": u} for s, u in pairs]})
    skill = ResearchBusiness(meta())

    from app.providers.tavily import SearchResult

    results = [SearchResult(title="t", url=REAL_URL, snippet="s")]
    brief = skill._parse(raw, "Acme", results)

    assert all(f.source_url == REAL_URL for f in brief.facts)
    assert len(brief.facts) + len(brief.open_unknowns) == len(
        [s for s, _ in pairs if s.strip()]
    ), "a claim was neither kept nor demoted"


# ── Malformed model output must not take down the turn ───────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "presence", [[1, 2], "a website", 42, None, True, {"website": None}]
)
def test_a_non_object_digital_presence_does_not_raise(presence):
    """Review finding. ``(presence or {}).get(...)`` raised AttributeError on a
    list, a string or a number — taking down the whole turn, which is exactly
    what the degraded path exists to avoid.
    """
    skill = ResearchBusiness(meta())
    raw = json.dumps({"facts": [], "digital_presence": presence})

    brief = skill._parse(raw, "Acme", [])

    assert brief.digital_presence.website is None


@pytest.mark.unit
def test_a_string_social_profiles_is_not_split_into_characters():
    """The quieter half of the same finding, and the worse one.

    Iterating a string yields single characters, so "twitter" became eight
    one-letter "profiles" carried into the brief as if they were data. A crash
    gets noticed; this would not have.
    """
    skill = ResearchBusiness(meta())
    raw = json.dumps({"facts": [], "digital_presence": {"social_profiles": "twitter"}})

    brief = skill._parse(raw, "Acme", [])

    assert brief.digital_presence.social_profiles == []


@pytest.mark.unit
def test_a_well_formed_digital_presence_still_reads():
    """The guard must not reject the shape it sits in front of."""
    skill = ResearchBusiness(meta())
    raw = json.dumps(
        {
            "facts": [],
            "digital_presence": {
                "website": "https://k.example",
                "social_profiles": ["https://x.com/k", "  ", "https://ig.com/k"],
                "notes": "active",
            },
        }
    )

    presence = skill._parse(raw, "Acme", []).digital_presence

    assert presence.website == "https://k.example"
    assert presence.social_profiles == ["https://x.com/k", "https://ig.com/k"]
    assert presence.notes == "active"
