"""Hypothesis property tests for RBAC enforcement on §13.3 endpoints (US-045).

Validates invariants across all endpoint/role combinations using
property-based testing. Complements the explicit unit tests in
test_dataset_endpoints_rbac.py with generative coverage.
"""

import pytest
from hypothesis import HealthCheck, given, settings as hypothesis_settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.auth.rbac import (
    Decision,
    Permission,
    Role,
    check_permission,
)

# §13.3 endpoint definitions: (method, path, permission, json_body)
SECTION_13_3_ENDPOINTS = [
    (
        "GET",
        "/v1/datasets/mra",
        Permission.VIEW,
        None,
    ),
    (
        "POST",
        "/v1/datasets/mra",
        Permission.REGISTER,
        {
            "prompt_name": "zorven-wf1-mra-system",
            "agent_code": "mra",
            "input_context": {"context_brand_name": "Test"},
            "expected_output": "Test output",
            "source": "manual",
            "metadata_extra": {"industry": "Tech"},
        },
    ),
    (
        "POST",
        "/v1/datasets/mra/mine",
        Permission.TRIGGER_OPTIMIZATION,
        None,
    ),
    (
        "PUT",
        "/v1/datasets/mra/99999",
        Permission.REGISTER,
        {"expected_output": "Updated"},
    ),
    (
        "DELETE",
        "/v1/datasets/mra/99999",
        Permission.MODIFY_CONFIG,
        None,
    ),
]


@pytest.fixture
async def api_client():
    """Async test client — lifespan disabled to isolate RBAC testing."""
    from app.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _call_endpoint(client, method, path, body, role):
    """Helper to call any endpoint with a given role header."""
    headers = {"X-User-Role": role} if role else {}
    if method == "GET":
        return await client.get(path, headers=headers)
    elif method == "POST":
        return await client.post(path, json=body or {}, headers=headers)
    elif method == "PUT":
        return await client.put(path, json=body or {}, headers=headers)
    elif method == "DELETE":
        return await client.delete(path, headers=headers)


class TestDatasetRbacProperties:
    @pytest.mark.asyncio
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=4),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_deny_always_produces_403(self, api_client, endpoint_idx, role):
        """If the RBAC matrix says DENY, the endpoint must return 403."""
        method, path, permission, body = SECTION_13_3_ENDPOINTS[endpoint_idx]
        resolved_role = Role(role)
        decision = check_permission(resolved_role, permission)

        if decision != Decision.DENY:
            return  # Only testing DENY cases

        resp = await _call_endpoint(api_client, method, path, body, role)
        assert resp.status_code == 403, (
            f"{method} {path} with role={role} should be 403 "
            f"(permission={permission.value}) but got {resp.status_code}"
        )

    @pytest.mark.asyncio
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=4),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_allow_or_escalate_never_produces_403(
        self, api_client, endpoint_idx, role
    ):
        """If the RBAC matrix says ALLOW or ESCALATE, endpoint must not return 403."""
        method, path, permission, body = SECTION_13_3_ENDPOINTS[endpoint_idx]
        resolved_role = Role(role)
        decision = check_permission(resolved_role, permission)

        if decision == Decision.DENY:
            return  # Only testing non-DENY cases

        resp = await _call_endpoint(api_client, method, path, body, role)
        assert resp.status_code != 403, (
            f"{method} {path} with role={role} should NOT be 403 "
            f"(decision={decision.value}) but got 403"
        )

    @pytest.mark.asyncio
    @given(
        role=st.from_regex(r"[a-zA-Z0-9]{1,20}", fullmatch=True).filter(
            lambda r: r.lower() not in {"owner", "admin", "editor", "viewer"}
        )
    )
    @hypothesis_settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_unknown_roles_behave_as_viewer(self, api_client, role):
        """Unknown role strings resolve to VIEWER — denied on REGISTER."""
        resp = await api_client.post(
            "/v1/datasets/mra",
            json={
                "prompt_name": "zorven-wf1-mra-system",
                "agent_code": "mra",
                "input_context": {"context_brand_name": "Test"},
                "expected_output": "Test output",
            },
            headers={"X-User-Role": role},
        )
        assert resp.status_code == 403, (
            f"Unknown role '{role}' should resolve to viewer and get 403 "
            f"on REGISTER, but got {resp.status_code}"
        )

    @pytest.mark.asyncio
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=4),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_deterministic_responses(self, api_client, endpoint_idx, role):
        """Same (endpoint, role) always produces the same status code."""
        method, path, permission, body = SECTION_13_3_ENDPOINTS[endpoint_idx]
        resp1 = await _call_endpoint(api_client, method, path, body, role)
        resp2 = await _call_endpoint(api_client, method, path, body, role)
        assert resp1.status_code == resp2.status_code, (
            f"Non-deterministic: {method} {path} role={role} "
            f"returned {resp1.status_code} then {resp2.status_code}"
        )

    @pytest.mark.asyncio
    async def test_all_section_13_3_routes_registered(self, api_client):
        """All §13.3 paths are registered in the FastAPI router."""
        from app.main import app

        registered_paths = {route.path for route in app.routes}
        expected_paths = {
            "/v1/datasets/{agent_code}",
            "/v1/datasets/{agent_code}/mine",
            "/v1/datasets/{agent_code}/{entry_id}",
        }
        for expected in expected_paths:
            assert expected in registered_paths, f"Missing §13.3 route: {expected}"
