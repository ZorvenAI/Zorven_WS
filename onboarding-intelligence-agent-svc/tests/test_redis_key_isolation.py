"""OIA shares Redis DB 2 with ten other services. This file is the guard.

ERRATA-01 is explicit that with a shared database, key-prefix isolation is
"the only mechanism keeping OIA's keys from colliding with ten other services"
and that this test "becomes more important, not less".

It asserts structurally — over every public key builder discovered by
reflection, not a hand-written list — so a builder added by a later story is
covered the moment it exists rather than when someone remembers to add a case.
"""

from __future__ import annotations

import inspect

import pytest

from app.cache import redis_manager
from app.cache.redis_manager import KEY_PREFIX, PROMPT_CACHE_PREFIX

pytestmark = pytest.mark.unit

TENANT = "tenant-alpha"

#: Every public callable in redis_manager whose name ends in _key.
KEY_BUILDERS = [
    (name, fn)
    for name, fn in inspect.getmembers(redis_manager, inspect.isfunction)
    if name.endswith("_key") and not name.startswith("_")
]


def call(fn) -> str:
    """Invoke a builder with plausible arguments for whatever it declares."""
    args = []
    for param in inspect.signature(fn).parameters:
        args.append(TENANT if param == "tenant_id" else f"val-{param}")
    return fn(*args)


def test_builders_were_discovered():
    """Guards the reflection itself — an empty sweep would pass vacuously."""
    assert len(KEY_BUILDERS) >= 6, [n for n, _ in KEY_BUILDERS]


@pytest.mark.parametrize("name,fn", KEY_BUILDERS, ids=[n for n, _ in KEY_BUILDERS])
def test_every_key_starts_with_the_service_prefix(name, fn):
    assert call(fn).startswith(KEY_PREFIX), f"{name} escapes the oia:v1: namespace"


@pytest.mark.parametrize("name,fn", KEY_BUILDERS, ids=[n for n, _ in KEY_BUILDERS])
def test_no_key_uses_another_services_namespace(name, fn):
    key = call(fn)
    for foreign in ("poi:", "prompt:", "bpa:", "coa:", "ila:", "tenant:", "celery"):
        assert not key.startswith(foreign), f"{name} writes into {foreign}"


@pytest.mark.parametrize("name,fn", KEY_BUILDERS, ids=[n for n, _ in KEY_BUILDERS])
def test_tenant_scoped_builders_carry_the_tenant(name, fn):
    """Circuit state is deliberately not tenant-scoped; everything else is."""
    if "tenant_id" not in inspect.signature(fn).parameters:
        assert name == "circuit_key", f"{name} is not tenant-scoped — is that right?"
        return
    assert f":{TENANT}:" in call(fn)


def test_tenant_config_key_was_renamed_under_the_service_prefix():
    """ERRATA-01 §4: tenant:{id}:oia:config → oia:v1:{tenant}:config."""
    key = redis_manager.tenant_config_key(TENANT)
    assert key == f"{KEY_PREFIX}{TENANT}:config"
    assert not key.startswith("tenant:")


def test_no_builder_accepts_an_empty_tenant():
    """A key without a tenant is a cross-tenant leak waiting to happen."""
    for name, fn in KEY_BUILDERS:
        if "tenant_id" not in inspect.signature(fn).parameters:
            continue
        with pytest.raises(ValueError):
            fn(
                *[
                    "" if p == "tenant_id" else "x"
                    for p in inspect.signature(fn).parameters
                ]
            )


def test_keys_are_distinct_across_builders():
    """Two builders must never collide on the same arguments."""
    keys = [call(fn) for _, fn in KEY_BUILDERS]
    assert len(keys) == len(set(keys))


def test_prompt_cache_prefix_is_foreign_and_read_only():
    """The poi: namespace belongs to prompt-optimization-svc."""
    assert not PROMPT_CACHE_PREFIX.startswith(KEY_PREFIX)
    writers = [
        name
        for name, fn in inspect.getmembers(redis_manager, inspect.isfunction)
        if name.endswith("_key") and call(fn).startswith(PROMPT_CACHE_PREFIX)
    ]
    assert writers == [], f"OIA must not build keys under poi:: {writers}"


def test_every_ttl_constant_is_positive_and_bounded():
    """ERRATA-01: an untrimmed key creates eviction pressure fleet-wide."""
    ttls = {
        name: value
        for name, value in vars(redis_manager).items()
        if name.startswith("TTL_")
    }
    assert ttls, "no TTL policy declared"
    for name, value in ttls.items():
        assert isinstance(value, int) and 0 < value <= 7 * 24 * 3600, name
