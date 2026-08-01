"""Unit tests for handshake authentication.

Real PyJWT tokens throughout — nothing is mocked. These prove the negative
paths that AC-1 depends on, and the tenant-claim rule from A-02's notes.
"""

import pytest

from echo.auth import AuthError, extract_token, validate
from harness.jwt_util import (
    DEFAULT_ISSUER,
    mint,
    mint_expired,
    mint_tenantless,
    mint_wrong_secret,
)

pytestmark = pytest.mark.unit

SECRET = "spike-secret"


def test_token_read_from_query_parameter():
    assert extract_token({"jwt": "abc"}, []) == "abc"


def test_token_read_from_subprotocol():
    assert extract_token({}, ["bearer.abc"]) == "abc"


def test_query_parameter_wins_when_both_present():
    assert extract_token({"jwt": "from-query"}, ["bearer.from-proto"]) == "from-query"


def test_absent_token_raises():
    with pytest.raises(AuthError):
        extract_token({}, [])


def test_empty_subprotocol_token_raises():
    with pytest.raises(AuthError):
        extract_token({}, ["bearer."])


def test_unrelated_subprotocol_is_ignored():
    with pytest.raises(AuthError):
        extract_token({}, ["graphql-ws"])


def test_valid_token_resolves_tenant():
    claims = validate(
        mint(SECRET, tenant_id="tenant-42"), SECRET, expected_issuer=DEFAULT_ISSUER
    )
    assert claims.tenant_id == "tenant-42"
    assert claims.issuer == DEFAULT_ISSUER
    assert claims.role == "Admin"


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        validate(mint_expired(SECRET), SECRET, expected_issuer=DEFAULT_ISSUER)


def test_forged_token_rejected():
    with pytest.raises(AuthError):
        validate(mint_wrong_secret(), SECRET, expected_issuer=DEFAULT_ISSUER)


def test_wrong_issuer_rejected():
    token = mint(SECRET, issuer="some-other-service")
    with pytest.raises(AuthError):
        validate(token, SECRET, expected_issuer=DEFAULT_ISSUER)


def test_tenantless_token_rejected():
    """A socket that opens but arrives tenant-less is a spike failure."""
    with pytest.raises(AuthError, match="tenant"):
        validate(mint_tenantless(SECRET), SECRET, expected_issuer=DEFAULT_ISSUER)


def test_garbage_token_rejected():
    with pytest.raises(AuthError):
        validate("not-a-jwt", SECRET, expected_issuer=DEFAULT_ISSUER)


def test_alg_none_token_rejected():
    """An unsigned token must not authenticate."""
    import jwt as pyjwt

    unsigned = pyjwt.encode(
        {"iss": DEFAULT_ISSUER, "tenant_id": "t", "exp": 9999999999},
        key="",
        algorithm="none",
    )
    with pytest.raises(AuthError):
        validate(unsigned, SECRET, expected_issuer=DEFAULT_ISSUER)
