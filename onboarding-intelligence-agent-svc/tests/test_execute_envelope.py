"""C-01 · the PREP envelope, its auth, and its conversation state.

The C-01 card is firm about the envelope — "implement them exactly; C-02
through C-04 all ride this envelope" — so these assert §10.2.1's field names
rather than a shape that merely works.

What this story does *not* deliver is asserted too: no PREP skill runs yet,
because SKL-OIA-01 and 02 are C-02 and C-03. ``skill_id == "NONE"`` says so
in the response rather than leaving a caller to infer it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import REQUIRED_ENV

SERVICE_TOKEN = REQUIRED_ENV.get("OIA_SERVICE_TOKEN", "")
EXECUTE = "/v1/execute"


def unique(prefix: str) -> str:
    """A fresh id per test.

    These run against a real Redis — no mocks — and the chat keys outlive the
    process. Fixed ids made "this conversation has one turn" depend on how
    many times the suite had been run, which passed once and then never again.
    """
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def valid_body(**overrides) -> dict:
    body = {
        "tenant_context": {
            "tenant_id": unique("t"),
            "user_id": "u-1",
            "role": "ADMIN",
            "trace_id": "01J8TRACE",
            "correlation_id": "01J8CORR",
        },
        "chat_session_id": unique("chat"),
        "input_prompt": "We're onboarding a coffee roaster in Pune.",
        "input_context": {"company_name": "Kalyani Roasters", "depth": 4},
        "config": {"language": "en-IN"},
        "previous_outputs": {},
    }
    body.update(overrides)
    return body


@pytest.fixture
def client(app_with_live_redis):
    """As a context manager, so the lifespan runs.

    Without it app.state.settings and app.state.redis are never set — the
    app object exists but nothing has wired it up, and every request fails
    on an attribute that production would always have.
    """
    with TestClient(app_with_live_redis) as test_client:
        yield test_client


def headers(token: str | None = SERVICE_TOKEN) -> dict:
    return {"X-Service-Token": token} if token is not None else {}


# ── The §10.2.1 envelope ─────────────────────────────────────────────


def test_execute_envelope(client):
    """The card's named case: request and response match §10.2.1."""
    response = client.post(EXECUTE, json=valid_body(), headers=headers())

    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {
        "status",
        "skill_id",
        "prompt_version",
        "output",
        "guardrails",
        "usage",
    }
    assert body["status"] == "SUCCEEDED"
    assert set(body["guardrails"]) == {"input", "plan", "output"}
    assert set(body["usage"]) == {"input_tokens", "output_tokens", "duration_ms"}


def test_the_response_says_plainly_that_no_skill_ran(client):
    """C-02 and C-03 bring the skills. Until then a caller must be able to
    tell "nothing is wired up" from "a skill ran and produced nothing"."""
    body = client.post(EXECUTE, json=valid_body(), headers=headers()).json()

    assert body["skill_id"] == "NONE"
    assert "SKL-OIA-01" in body["output"]["detail"]


@pytest.mark.parametrize(
    "missing", ["tenant_context", "chat_session_id", "input_prompt"]
)
def test_a_required_field_is_refused(client, missing):
    body = valid_body()
    del body[missing]

    assert client.post(EXECUTE, json=body, headers=headers()).status_code == 422


def test_an_unknown_field_is_refused(client):
    """extra="forbid": a caller's typo should fail loudly, not be dropped —
    three later stories build against this envelope."""
    response = client.post(
        EXECUTE, json=valid_body(inputPrompt="camelCase typo"), headers=headers()
    )

    assert response.status_code == 422


def test_an_unknown_role_is_refused(client):
    body = valid_body()
    body["tenant_context"]["role"] = "SUPERUSER"

    assert client.post(EXECUTE, json=body, headers=headers()).status_code == 422


def test_session_id_is_optional(client):
    """A prep conversation starts before an OnboardingSession exists — that is
    the point of preparing in the chat the operator already uses."""
    response = client.post(EXECUTE, json=valid_body(), headers=headers())

    assert response.status_code == 200
    assert "session_id" not in valid_body()


# ── X-Service-Token (§10.2, §15) ─────────────────────────────────────


def test_a_missing_token_is_refused(client):
    assert client.post(EXECUTE, json=valid_body(), headers={}).status_code == 401


def test_a_wrong_token_is_refused(client):
    response = client.post(EXECUTE, json=valid_body(), headers=headers("nope"))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "ERR-20"


def test_an_empty_token_is_refused(client):
    assert (
        client.post(EXECUTE, json=valid_body(), headers=headers("")).status_code == 401
    )


def test_auth_runs_before_validation(client):
    """An unauthenticated caller must not learn which fields are required.

    A 422 here would turn the endpoint into a schema oracle for anyone who
    can reach it.
    """
    response = client.post(EXECUTE, json={"garbage": True}, headers={})

    assert response.status_code == 401


def test_an_unconfigured_service_refuses_everything(monkeypatch, app_with_live_redis):
    """A service that authenticates nothing because its config is missing is
    the failure mode that looks fine in staging."""
    with TestClient(app_with_live_redis) as test_client:
        app_with_live_redis.state.settings.SERVICE_TOKEN = ""
        response = test_client.post(EXECUTE, json=valid_body(), headers=headers())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ERR-21", (
        "a misconfigured service must not report itself as a caller auth "
        "failure — that sends an operator to the wrong runbook"
    )


# ── AC-2 · conversation state, as mechanism ──────────────────────────


def test_multi_turn_history_accumulates(client):
    """AC-2's mechanism half: a later turn sees the earlier ones.

    Resolving "make the third question deeper" against that history needs a
    questionnaire and a skill — C-02 and C-03. This is the state they will
    read.
    """
    body = valid_body(chat_session_id=unique("chat"))

    first = client.post(EXECUTE, json=body, headers=headers()).json()
    assert first["output"]["turns"] == 1

    body["input_prompt"] = "Go deeper on their supply chain."
    second = client.post(EXECUTE, json=body, headers=headers()).json()

    assert second["output"]["turns"] == 2
    texts = [turn["text"] for turn in second["output"]["history"]]
    assert texts[0] == "We're onboarding a coffee roaster in Pune."
    assert texts[1] == "Go deeper on their supply chain."


def test_conversations_do_not_bleed_between_chats(client):
    client.post(
        EXECUTE, json=valid_body(chat_session_id=unique("chat")), headers=headers()
    )
    other = client.post(
        EXECUTE, json=valid_body(chat_session_id=unique("chat")), headers=headers()
    ).json()

    assert other["output"]["turns"] == 1


def test_conversations_do_not_bleed_between_tenants(client):
    body = valid_body(chat_session_id=unique("chat"))
    client.post(EXECUTE, json=body, headers=headers())

    body["tenant_context"]["tenant_id"] = unique("t")
    other = client.post(EXECUTE, json=body, headers=headers()).json()

    assert other["output"]["turns"] == 1, "a tenant saw another tenant's chat"


@pytest.mark.integration
async def test_the_chat_key_carries_a_ttl():
    """An untimed key on a shared Redis is a slow leak — the card's words, and
    ERRATA-01's rule since DB 2 is shared with ten other services.

    Builds its own RedisManager rather than borrowing the app's: TestClient
    drives the lifespan on its own event loop, and awaiting that connection
    from an async test attaches a future to a different loop.
    """
    from app.cache.conversation import ConversationStore
    from app.cache.redis_manager import TTL_CHAT, RedisManager
    from app.core.config import get_settings

    manager = RedisManager(get_settings())
    await manager.connect()
    try:
        store = ConversationStore(manager)
        tenant, chat = unique("t"), unique("c")

        await store.append(
            tenant_id=tenant, chat_session_id=chat, role="operator", text="hello"
        )
        ttl = await manager.client.ttl(manager.keys_for(tenant).chat(chat))

        assert 0 < ttl <= TTL_CHAT
        await store.clear(tenant_id=tenant, chat_session_id=chat)
    finally:
        await manager.close()


# ── The code and the status must agree with the taxonomy ─────────────


@pytest.mark.parametrize(
    "make_request,expected_code",
    [
        (lambda c: c.post(EXECUTE, json=valid_body(), headers={}), "ERR-20"),
        (
            lambda c: c.post(EXECUTE, json=valid_body(), headers=headers("nope")),
            "ERR-20",
        ),
        (lambda c: c.post(EXECUTE, json=valid_body(), headers=headers("")), "ERR-20"),
    ],
)
def test_an_auth_refusal_matches_its_own_spec(client, make_request, expected_code):
    """C-01 shipped ERR-01 ("Invalid or expired JWT", 401) on a 503 branch.

    The status happened to match on one of the two paths, which is why it read
    as fine. Asserting the response against ERROR_SPECS rather than against a
    hardcoded number is what makes the mismatch visible.
    """
    from app.core.errors import ERROR_SPECS, ErrorCode

    response = make_request(client)
    code = response.json()["detail"]["code"]

    assert code == expected_code
    spec = ERROR_SPECS[ErrorCode(code)]
    assert response.status_code == spec.http_status, (
        f"{code} responded {response.status_code} but its spec says "
        f"{spec.http_status}"
    )


def test_service_token_failures_do_not_reuse_the_jwt_code(client):
    """§18.4 reserves ERR-01 for JWT. This endpoint has no JWT to be invalid —
    reporting one sends operators looking at the wrong subsystem."""
    for hdrs in ({}, headers("nope"), headers("")):
        body = client.post(EXECUTE, json=valid_body(), headers=hdrs).json()
        assert body["detail"]["code"] != "ERR-01"
