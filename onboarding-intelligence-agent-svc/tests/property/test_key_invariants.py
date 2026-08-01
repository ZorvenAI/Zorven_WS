"""Property tests for the Redis key namespace.

The example-based tests in test_redis_key_isolation.py check the tenant ids we
thought of. These check the ones we did not — unicode, colons, very long ids,
ids that look like another service's prefix.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.cache.redis_manager import (
    KEY_PREFIX,
    circuit_key,
    idempotency_key,
    live_frames_key,
    live_lock_key,
    session_key,
    tenant_config_key,
)

pytestmark = pytest.mark.property

# Any non-empty identifier, including ones designed to be awkward.
identifiers = st.text(min_size=1, max_size=64).filter(lambda s: s.strip() != "")

TENANT_BUILDERS = [session_key, live_frames_key, live_lock_key, idempotency_key]


@given(tenant=identifiers, other=identifiers)
def test_two_argument_builders_stay_in_the_namespace(tenant, other):
    for build in TENANT_BUILDERS:
        assert build(tenant, other).startswith(KEY_PREFIX)


@given(tenant=identifiers)
def test_single_argument_builders_stay_in_the_namespace(tenant):
    assert tenant_config_key(tenant).startswith(KEY_PREFIX)


@given(dependency=identifiers)
def test_circuit_keys_stay_in_the_namespace(dependency):
    """Not tenant-scoped, but never readable as another service's state."""
    key = circuit_key(dependency)
    assert key.startswith(KEY_PREFIX)
    assert key.startswith(f"{KEY_PREFIX}circuit:")


@given(tenant=identifiers, other=identifiers)
def test_tenant_appears_in_every_tenant_scoped_key(tenant, other):
    for build in TENANT_BUILDERS:
        assert tenant in build(tenant, other)


@given(a=identifiers, b=identifiers, other=identifiers)
def test_different_tenants_never_share_a_key(a, b, other):
    """The whole point of the namespace: no cross-tenant read is possible."""
    if a == b:
        return
    for build in TENANT_BUILDERS:
        assert build(a, other) != build(b, other)


@given(tenant=identifiers, x=identifiers, y=identifiers)
def test_different_resources_never_share_a_key(tenant, x, y):
    if x == y:
        return
    for build in TENANT_BUILDERS:
        assert build(tenant, x) != build(tenant, y)


@given(tenant=identifiers, other=identifiers)
@settings(max_examples=200)
def test_builders_do_not_collide_with_each_other(tenant, other):
    keys = [build(tenant, other) for build in TENANT_BUILDERS]
    assert len(keys) == len(set(keys))


@given(
    tenant=st.sampled_from(["poi", "prompt", "celery", "tenant", "bpa", "coa"]),
    other=identifiers,
)
def test_a_tenant_named_after_another_service_still_stays_namespaced(tenant, other):
    """A tenant id colliding with a foreign prefix must not escape ours."""
    for build in TENANT_BUILDERS:
        key = build(tenant, other)
        assert key.startswith(KEY_PREFIX)
        assert not key.startswith(f"{tenant}:")


@given(other=identifiers)
def test_empty_tenant_is_always_rejected(other):
    for build in TENANT_BUILDERS:
        with pytest.raises(ValueError):
            build("", other)
