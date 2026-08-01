"""Property tests for the Redis key namespace.

The example-based tests in test_redis_key_isolation.py check the tenant ids we
thought of. These check the ones we did not — unicode, colons, very long ids,
and ids that look like another service's prefix.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.cache.redis_manager import KEY_PREFIX, TenantKeys, circuit_key

pytestmark = pytest.mark.property

identifiers = st.text(min_size=1, max_size=64).filter(lambda s: s.strip() != "")

#: (method name, number of arguments it takes beyond self)
ONE_ARG = [
    "session",
    "session_summary",
    "transcript",
    "questions",
    "coverage",
    "live_lock",
    "idempotency",
    "outbox",
    "ratelimit",
]


@given(tenant=identifiers, other=identifiers)
def test_every_key_stays_in_the_namespace(tenant, other):
    keys = TenantKeys(tenant)
    for name in ONE_ARG:
        assert getattr(keys, name)(other).startswith(KEY_PREFIX)
    assert keys.config().startswith(KEY_PREFIX)


@given(tenant=identifiers, other=identifiers)
def test_tenant_appears_in_every_key(tenant, other):
    keys = TenantKeys(tenant)
    for name in ONE_ARG:
        assert tenant in getattr(keys, name)(other)


@given(a=identifiers, b=identifiers, other=identifiers)
def test_different_tenants_never_share_a_key(a, b, other):
    """The whole point of the namespace: no cross-tenant read is possible."""
    if a == b:
        return
    for name in ONE_ARG:
        assert getattr(TenantKeys(a), name)(other) != getattr(TenantKeys(b), name)(
            other
        )


@given(tenant=identifiers, x=identifiers, y=identifiers)
def test_different_resources_never_share_a_key(tenant, x, y):
    if x == y:
        return
    keys = TenantKeys(tenant)
    for name in ONE_ARG:
        assert getattr(keys, name)(x) != getattr(keys, name)(y)


@given(tenant=identifiers, other=identifiers)
@settings(max_examples=200)
def test_builders_do_not_collide_with_each_other(tenant, other):
    keys = TenantKeys(tenant)
    built = [getattr(keys, name)(other) for name in ONE_ARG] + [keys.config()]
    assert len(built) == len(set(built))


@given(
    tenant=st.sampled_from(["poi", "prompt", "celery", "tenant", "bpa", "coa"]),
    other=identifiers,
)
def test_a_tenant_named_after_another_service_still_stays_namespaced(tenant, other):
    """A tenant id colliding with a foreign prefix must not escape ours."""
    keys = TenantKeys(tenant)
    for name in ONE_ARG:
        key = getattr(keys, name)(other)
        assert key.startswith(KEY_PREFIX)
        assert not key.startswith(f"{tenant}:")


@given(blank=st.sampled_from(["", " ", "\t", "   "]))
def test_a_blank_tenant_is_always_rejected(blank):
    with pytest.raises(ValueError):
        TenantKeys(blank)


@given(dependency=identifiers)
def test_circuit_keys_stay_in_the_namespace_without_a_tenant(dependency):
    key = circuit_key(dependency)
    assert key.startswith(f"{KEY_PREFIX}circuit:")
