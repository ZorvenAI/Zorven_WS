"""JWT handling for the WebSocket handshake.

The constraint that shapes this module: **browsers cannot set an
Authorization header on a WebSocket handshake.** The WebSocket API accepts no
custom headers, so the token has to travel another way. Two carriers are
viable and both are implemented here so the spike can compare them:

``?jwt=<token>``
    A query parameter. Kong's JWT plugin reads this natively via
    ``uri_param_names`` (default ``jwt``), so the gateway can reject a bad
    token *before* it reaches the service. Downside: the token lands in access
    logs and browser history.

``Sec-WebSocket-Protocol: bearer.<token>``
    A subprotocol value. Keeps the token out of the URL, but Kong's JWT plugin
    cannot read it without a custom plugin, so on the gateway path the check
    would have to move into the service anyway.

On Cloud Run there is no gateway at all, so validation happens here regardless
of carrier — which is exactly the cost A-02 has to quantify for F-04.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

SUBPROTOCOL_PREFIX = "bearer."


class AuthError(Exception):
    """Raised when a handshake token is missing, malformed or invalid.

    Always maps to close code 4401 — the caller does not get to distinguish
    "expired" from "forged" from "absent", because telling an unauthenticated
    caller why they failed is free reconnaissance.
    """


@dataclass(frozen=True)
class TenantClaims:
    tenant_id: str
    subject: str
    issuer: str
    role: str | None = None


def extract_token(
    query_params: dict[str, str], subprotocols: list[str] | None = None
) -> str:
    """Pull the bearer token out of whichever carrier the client used."""
    token = query_params.get("jwt")
    if token:
        return token

    for proto in subprotocols or []:
        if proto.startswith(SUBPROTOCOL_PREFIX):
            candidate = proto[len(SUBPROTOCOL_PREFIX) :]
            if candidate:
                return candidate

    raise AuthError("no token presented")


def validate(
    token: str,
    secret: str,
    *,
    expected_issuer: str,
    algorithms: tuple[str, ...] = ("HS256",),
) -> TenantClaims:
    """Validate signature, expiry and issuer, and resolve the tenant.

    A token that verifies but carries no tenant is a failure, not a
    tenant-less success: A-02's technical notes call a socket that opens but
    arrives tenant-less a failure of the spike, not a later story's problem.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=list(algorithms),
            issuer=expected_issuer,
            options={"require": ["exp", "iss"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError(str(exc)) from exc

    tenant_id = payload.get("tenant_id") or payload.get("tenant")
    if not tenant_id:
        raise AuthError("token carries no tenant claim")

    return TenantClaims(
        tenant_id=str(tenant_id),
        subject=str(payload.get("sub", "")),
        issuer=str(payload["iss"]),
        role=payload.get("role"),
    )


def authenticate(
    query_params: dict[str, str],
    subprotocols: list[str] | None,
    secret: str,
    *,
    expected_issuer: str,
) -> TenantClaims:
    """Extract and validate in one step."""
    return validate(
        extract_token(query_params, subprotocols),
        secret,
        expected_issuer=expected_issuer,
    )
