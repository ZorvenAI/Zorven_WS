"""End-to-end: an operator's prep turn, through the real image.

Named by two cards — C-02's "Brief step" and C-03's ``test_count_honoured``.
Both are here because neither is meaningful alone: the count is honoured on a
questionnaire built from a brief, and the brief only matters because something
turns it into questions.

**This is the test that found the gap it was written for.** Everything in C-03
passed while ``PrepExecutor.generate_questionnaire`` had no caller —
``/v1/execute`` still only ran research, so AC-1 had no path from the
operator's chat. Unit and integration tests both passed because both called
the executor directly. Only driving the deployed artefact over HTTP the way
Django does could show it.

Real everything: the built image, a real Redis, a real Gemini key, and Tavily
when one is configured. Skips when the pieces are absent; **fails** rather than
skips when ``OIA_TEST_E2E`` says they should be present, following the same
asymmetry as the Kafka round-trip tests. A green run that silently covered
nothing is worse than an honest red.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.conftest import free_port

pytestmark = [pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "zorven-oia-prep-e2e:test"
CONTAINER = "oia-prep-e2e"
SERVICE_TOKEN = "e2e-service-token"


def _required(name: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _skip_or_fail(reason: str) -> None:
    """Skip locally, fail where the environment claims to be complete."""
    if os.environ.get("OIA_TEST_E2E"):
        pytest.fail(f"OIA_TEST_E2E is set but {reason}")
    pytest.skip(reason)


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode
        == 0
    )


@pytest.fixture(scope="module")
def gemini_key() -> str:
    key = _required("OIA_GEMINI_KEY", "GOOGLE_API_KEY")
    if not key:
        _skip_or_fail("no Gemini key is configured — nothing would be generated")
    return key


@pytest.fixture(scope="module")
def image() -> str:
    if not docker_available():
        _skip_or_fail("docker is not available")
    build = subprocess.run(
        ["docker", "build", "-t", IMAGE, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    return IMAGE


@pytest.fixture(scope="module")
def agent(image, gemini_key) -> str:
    """The image running as it deploys, with the keys it deploys with."""
    port = free_port()
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)

    env = [
        "OIA_BACKEND_BASE_URL=" + (_required("OIA_TEST_BACKEND_URL") or "PLACEHOLDER"),
        "OIA_GCS_BUCKET=zorven-raw-assets",
        "OIA_REDIS_URL=redis://host.docker.internal:6379/2",
        f"OIA_SERVICE_TOKEN={SERVICE_TOKEN}",
        f"OIA_GEMINI_KEY={gemini_key}",
        # Optional. Without it research degrades — which the brief step
        # asserts explicitly rather than skipping, because a degraded brief is
        # a supported outcome (C-02 AC-3), not a broken test.
        f"OIA_TAVILY_API_KEY={_required('OIA_TAVILY_API_KEY', 'TAVILY_API_KEY')}",
    ]
    command = [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER,
        "-p",
        f"{port}:8120",
        "--add-host",
        "host.docker.internal:host-gateway",
    ]
    for pair in env:
        command += ["-e", pair]
    command.append(image)

    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr

    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for(base)
        yield base
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)


def _wait_for(base: str, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=3).status_code in (200, 503):
                return
        except Exception:  # noqa: BLE001 — retried until the deadline
            time.sleep(1)
    logs = subprocess.run(
        ["docker", "logs", "--tail", "60", CONTAINER], capture_output=True, text=True
    )
    raise RuntimeError(f"agent never answered:\n{logs.stdout}\n{logs.stderr}")


def unique(prefix: str) -> str:
    """Redis outlives the container; a fixed id makes a rerun read stale state."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def prep_turn(agent: str, **overrides) -> dict:
    """One PREP turn, exactly as Django's dispatcher sends it."""
    body = {
        "tenant_context": {
            "tenant_id": unique("t"),
            "user_id": "u-1",
            "role": "ADMIN",
            "trace_id": unique("trace"),
        },
        "chat_session_id": unique("chat"),
        "input_prompt": "Prep the onboarding call for this coffee roaster.",
        "input_context": {
            "company_name": "Kalyani Roasters",
            "website": "https://example.com",
            "industry": "speciality coffee",
            "operator_notes": "Family run, wants to sell online.",
        },
    }
    body["input_context"].update(overrides.pop("input_context", {}))
    body.update(overrides)

    response = httpx.post(
        f"{agent}/v1/execute",
        json=body,
        headers={"X-Service-Token": SERVICE_TOKEN},
        # Generous: §2.1 gives PREP 60 s, and this is a real search plus a
        # real generation on a cold container.
        timeout=180,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── C-02's Brief step ────────────────────────────────────────────────


def test_a_prep_turn_produces_a_reachable_brief(agent):
    """C-02's named e2e case: "The brief is reachable from the session".

    Asserts the *shape and the honesty* of the brief rather than its content —
    the web moves and the model is not deterministic, so asserting on facts
    would make this a flake generator. What must hold on every run is that
    nothing is asserted without a source, and that a thin brief says it is
    thin.
    """
    body = prep_turn(agent)
    brief = body["output"]["research_brief"]

    assert body["skill_id"] == "SKL-OIA-01"
    assert set(brief) >= {
        "company_name",
        "facts",
        "open_unknowns",
        "degraded",
        "sources",
    }
    assert brief["company_name"] == "Kalyani Roasters"

    # AC-1, through the real stack: every asserted fact carries a source.
    for fact in brief["facts"]:
        assert fact["source_url"].startswith(("http://", "https://")), fact

    # AC-3: if research could not run, the brief says so and asserts nothing.
    if brief["degraded"]:
        assert brief["degraded_reason"]
        assert brief["facts"] == []
        assert brief["open_unknowns"], "a degraded brief still owes questions"


SENTENCE_ENDINGS = (".", ".)", "?", "!")


def test_the_chat_reply_is_a_sentence_not_a_payload(agent):
    """``output.detail`` is what Django renders into the chat bubble."""
    detail = prep_turn(agent)["output"]["detail"]

    assert detail and detail.endswith(SENTENCE_ENDINGS)
    for leak in ("Traceback", "{", "None"):
        assert leak not in detail


def test_the_second_turn_is_served_from_cache(agent):
    """AC-2 over HTTP: the same business is not researched twice.

    The cache is keyed on (tenant, normalised name), so the second turn reuses
    the tenant and retypes the company name differently — which is what an
    operator tuning question count actually does, and each re-run is otherwise
    a fresh round of paid search.
    """
    tenant = unique("t")
    first = prep_turn(
        agent,
        tenant_context={
            "tenant_id": tenant,
            "user_id": "u",
            "role": "ADMIN",
            "trace_id": unique("tr"),
        },
    )
    if first["output"]["research_brief"]["degraded"]:
        pytest.skip("research degraded, so nothing was cached — by design")

    second = prep_turn(
        agent,
        tenant_context={
            "tenant_id": tenant,
            "user_id": "u",
            "role": "ADMIN",
            "trace_id": unique("tr"),
        },
        input_context={"company_name": "  kalyani roasters Pvt. Ltd. "},
    )

    assert second["output"]["from_cache"] is True


# ── C-03's test_count_honoured ───────────────────────────────────────


@pytest.mark.parametrize("count", [12, 5])
def test_count_honoured(agent, count):
    """C-03's named e2e case: "Asking for 12 yields 12".

    Through the real image, a real model and the real route — which is what
    makes it worth having. Every C-03 unit test passed while this path did not
    exist, because they all called the executor directly.
    """
    body = prep_turn(agent, input_context={"count": count, "depth": "standard"})

    assert body["skill_id"] == "SKL-OIA-02"
    questionnaire = body["output"]["questionnaire"]
    assert questionnaire is not None, "no questionnaire was generated"
    assert len(questionnaire["questions"]) == count


def test_every_question_is_tagged_for_a_workflow(agent):
    """AC-2 through the real model."""
    body = prep_turn(agent, input_context={"count": 9})
    questions = body["output"]["questionnaire"]["questions"]

    assert questions
    for question in questions:
        assert question["workflow_target"] in {"WF1", "WF2", "WF3"}
        assert question["text"].strip()


def test_wf3_is_covered_by_a_real_generation(agent):
    """The clause the requirement review added, and the one a model silently
    drops back to brand-strategy questions without. The prompt carries it and
    the top-up guarantees it; this proves the combination against a real
    model rather than against a fixture.
    """
    questionnaire = prep_turn(agent, input_context={"count": 12})["output"][
        "questionnaire"
    ]

    workflows = {q["workflow_target"] for q in questionnaire["questions"]}
    assert "WF3" in workflows, f"only {sorted(workflows)} were generated"


def test_coverage_is_reported_with_the_questions(agent):
    """AC-3: visible before the meeting, in the same turn as the set."""
    questionnaire = prep_turn(agent, input_context={"count": 9})["output"][
        "questionnaire"
    ]

    assert set(questionnaire["coverage"]) == {"WF1", "WF2", "WF3"}
    assert sum(questionnaire["coverage"].values()) == pytest.approx(1.0)


def test_a_turn_without_a_count_generates_nothing(agent):
    """`count` is the trigger. A turn that only asks for research must not
    silently spend a generation — and must still answer."""
    body = prep_turn(agent)

    assert body["output"]["questionnaire"] is None
    assert body["skill_id"] == "SKL-OIA-01"
    assert body["output"]["research_brief"]


def test_a_deep_set_differs_from_a_quick_one(agent):
    """FR-PREP-04: "depth changes the research budget, not the count".

    Compared by their own rubric rather than by eye, and asserted loosely: the
    model is not deterministic and this is the real one. The claim is only
    that deep produces measurably more probing questions than quick — if that
    stops being true, the depth control has become decoration.
    """
    import json as _json

    rubric = _json.loads(
        (ROOT / "tests" / "fixtures" / "depth_rubric.json").read_text()
    )

    def deep_fraction(questions: list[dict]) -> float:
        markers = rubric["deep_markers"]
        hits = 0
        for question in questions:
            lowered = question["text"].strip().lower()
            if any(lowered.startswith(p) for p in markers["prefixes"]) or any(
                c in lowered for c in markers["contains"]
            ):
                hits += 1
        return hits / len(questions) if questions else 0.0

    quick = prep_turn(agent, input_context={"count": 8, "depth": "quick"})
    deep = prep_turn(agent, input_context={"count": 8, "depth": "deep"})

    quick_score = deep_fraction(quick["output"]["questionnaire"]["questions"])
    deep_score = deep_fraction(deep["output"]["questionnaire"]["questions"])

    assert deep_score > quick_score, (
        f"deep scored {deep_score:.2f} against quick's {quick_score:.2f} — "
        "the depth control is not changing the questions"
    )


# ── The whole path, once ─────────────────────────────────────────────


def test_prep_to_questionnaire(agent):
    """The journey the file is named for, in one turn.

    An operator opens a chat, names a business, asks for twelve questions, and
    gets a sourced brief, twelve tagged questions, coverage, and a sentence to
    read — from the deployed artefact.
    """
    body = prep_turn(agent, input_context={"count": 12, "depth": "standard"})
    output = body["output"]

    assert output["research_brief"]["company_name"] == "Kalyani Roasters"
    assert len(output["questionnaire"]["questions"]) == 12
    assert output["questionnaire"]["coverage"]
    # ".)" is a sentence ending too. The first version of this asserted a
    # bare "." and failed on the perfectly correct
    #   "... coverage WF3 33%. (not saved — ... could not be stored.)"
    # which is the agent telling the truth about a backend this test does not
    # run. The assertion was wrong, not the message.
    assert output["detail"].endswith(SENTENCE_ENDINGS)
    assert body["guardrails"] == {"input": "PASS", "plan": "PASS", "output": "PASS"}


def test_an_unreachable_backend_is_admitted_in_the_reply(agent):
    """AC-4 says a DRAFT row exists. This harness runs the agent with no
    Django — OIA_BACKEND_BASE_URL is PLACEHOLDER unless OIA_TEST_BACKEND_URL
    is set — so storage genuinely fails here, and the operator must be told.

    Promoted from an incidental to a covered case: the "(not saved)" suffix
    turned up as a surprise in an unrelated assertion, which means nothing was
    checking the behaviour it represents. Telling someone "12 questions ready"
    when nothing was stored sends them to an approval screen with nothing on
    it.
    """
    if os.environ.get("OIA_TEST_BACKEND_URL"):
        pytest.skip("a real backend is configured, so storage should succeed")

    output = prep_turn(agent, input_context={"count": 6})["output"]

    assert len(output["questionnaire"]["questions"]) == 6
    assert output["stored_questionnaire_id"] is None
    assert "not saved" in output["detail"]
