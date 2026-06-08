"""Hypothesis property tests for RBAC enforcement on §13.2 endpoints (US-044).

Validates invariants across all endpoint/role combinations using
property-based testing. Complements the explicit unit tests in
test_optimization_endpoints_rbac.py with generative coverage.
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
    resolve_role,
)

# §13.2 endpoint definitions: (method, path, permission, json_body, owner_only)
# owner_only=True means the endpoint has a custom OWNER-only check beyond RBAC
SECTION_13_2_ENDPOINTS = [
    (
        "POST",
        "/v1/optimize/agent/mra",
        Permission.TRIGGER_OPTIMIZATION,
        None,
        False,
    ),
    (
        "POST",
        "/v1/optimize/group/wf1-discovery-pipeline",
        Permission.TRIGGER_OPTIMIZATION,
        None,
        False,
    ),
    (
        "POST",
        "/v1/optimize/all",
        None,  # Custom OWNER-only check, not in RBAC matrix
        None,
        True,
    ),
    (
        "GET",
        "/v1/optimize/runs",
        Permission.VIEW,
        None,
        False,
    ),
    (
        "GET",
        "/v1/optimize/runs/test-run-1",
        Permission.VIEW,
        None,
        False,
    ),
    (
        "POST",
        "/v1/optimize/runs/test-run-1/approve",
        Permission.APPROVE,
        {"approved_by": "test-user"},
        False,
    ),
    (
        "POST",
        "/v1/optimize/runs/test-run-1/reject",
        Permission.APPROVE,
        {"approved_by": "test-user", "reason": "Not ready"},
        False,
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


class TestOptimizationRbacProperties:
    @pytest.mark.asyncio
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=6),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=28,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_deny_always_produces_403(self, api_client, endpoint_idx, role):
        """If the RBAC matrix says DENY, the endpoint must return 403."""
        method, path, permission, body, owner_only = SECTION_13_2_ENDPOINTS[
            endpoint_idx
        ]

        if owner_only:
            # /optimize/all has custom OWNER-only check
            if role != "owner":
                resp = await _call_endpoint(api_client, method, path, body, role)
                assert resp.status_code == 403, (
                    f"{method} {path} with role={role} should be 403 "
                    f"(OWNER-only) but got {resp.status_code}"
                )
            return

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
        endpoint_idx=st.integers(min_value=0, max_value=6),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=28,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_allow_or_escalate_never_produces_403(
        self, api_client, endpoint_idx, role
    ):
        """If the RBAC matrix says ALLOW or ESCALATE, endpoint must not return 403."""
        method, path, permission, body, owner_only = SECTION_13_2_ENDPOINTS[
            endpoint_idx
        ]

        if owner_only:
            # /optimize/all: only OWNER is allowed
            if role == "owner":
                resp = await _call_endpoint(api_client, method, path, body, role)
                assert resp.status_code != 403, (
                    f"{method} {path} with role=owner should NOT be 403 "
                    f"(OWNER-only) but got 403"
                )
            return

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
    async def test_optimize_all_is_owner_only(self, api_client):
        """AC-1 invariant: only OWNER can trigger /optimize/all."""
        for role in ["viewer", "editor", "admin"]:
            resp = await api_client.post(
                "/v1/optimize/all", headers={"X-User-Role": role}
            )
            assert resp.status_code == 403, (
                f"/optimize/all with role={role} should be 403 but got "
                f"{resp.status_code}"
            )

        resp = await api_client.post(
            "/v1/optimize/all", headers={"X-User-Role": "owner"}
        )
        assert (
            resp.status_code != 403
        ), "/optimize/all with role=owner should NOT be 403"

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
        """Unknown role strings resolve to VIEWER — denied on TRIGGER_OPTIMIZATION."""
        resp = await api_client.post(
            "/v1/optimize/agent/mra",
            headers={"X-User-Role": role},
        )
        assert resp.status_code == 403, (
            f"Unknown role '{role}' should resolve to viewer and get 403 "
            f"on TRIGGER_OPTIMIZATION, but got {resp.status_code}"
        )

    @pytest.mark.asyncio
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=6),
        role=st.sampled_from(["owner", "admin", "editor", "viewer"]),
    )
    @hypothesis_settings(
        max_examples=28,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_deterministic_responses(self, api_client, endpoint_idx, role):
        """Same (endpoint, role) always produces the same status code."""
        method, path, permission, body, owner_only = SECTION_13_2_ENDPOINTS[
            endpoint_idx
        ]
        resp1 = await _call_endpoint(api_client, method, path, body, role)
        resp2 = await _call_endpoint(api_client, method, path, body, role)
        assert resp1.status_code == resp2.status_code, (
            f"Non-deterministic: {method} {path} role={role} "
            f"returned {resp1.status_code} then {resp2.status_code}"
        )
