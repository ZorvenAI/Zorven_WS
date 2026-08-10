"""Google Calendar OAuth, Django-side only (D-02, Design §19).

The agent never sees any of this. §19: "Calendar sync is a Django concern; the
agent reads scheduled meetings." Keeping the exchange here means a compromise
of the agent cannot reach an operator's personal calendar.

Endpoint URLs are module constants read through :func:`_endpoints` rather than
inlined, so a test can point them at a local server and still run *this* code.
Real Google needs interactive consent, which no CI can give — and mocking the
functions in this module would test everything except the module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from decouple import config

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

#: Read plus event creation, and nothing else. The card is specific: a full
#: `calendar` grant would let this app delete an operator's own appointments.
SCOPE = "https://www.googleapis.com/auth/calendar.events"

TIMEOUT_S = 15


class OAuthError(Exception):
    """The exchange failed. Carries an operator-facing reason, never a token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Endpoints:
    auth: str = AUTH_URL
    token: str = TOKEN_URL
    revoke: str = REVOKE_URL


def _endpoints() -> Endpoints:
    """Google's endpoints, overridable for tests.

    ``GOOGLE_OAUTH_BASE`` is read through decouple like every other setting.
    Unset — which is production — it resolves to Google.
    """
    base = config("GOOGLE_OAUTH_BASE", default="").strip()
    if not base:
        return Endpoints()
    base = base.rstrip("/")
    return Endpoints(
        auth=f"{base}/auth", token=f"{base}/token", revoke=f"{base}/revoke"
    )


def client_credentials() -> tuple[str, str]:
    return (
        config("GOOGLE_OAUTH_CLIENT_ID", default=""),
        config("GOOGLE_OAUTH_CLIENT_SECRET", default=""),
    )


def is_configured() -> bool:
    """Whether this deployment can offer the connection at all.

    Absent credentials is a supported state, not an error: FR-CAL-01 promises
    the in-app calendar works with "zero external setup", so a deployment that
    never sets these keeps a working calendar and simply cannot connect Google.
    """
    client_id, client_secret = client_credentials()
    return bool(client_id and client_secret)


def authorisation_url(*, redirect_uri: str, state: str) -> str:
    """Where to send the operator's browser to consent."""
    client_id, _ = client_credentials()
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        # offline plus consent, or Google returns no refresh token on a repeat
        # authorisation — the connection would appear to work and then die at
        # the first expiry with nothing to refresh from.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_endpoints().auth}?{urlencode(query)}"


def exchange_code(*, code: str, redirect_uri: str) -> dict[str, str]:
    """Trade an authorisation code for tokens.

    Returns the parsed body. Raises :class:`OAuthError` on anything else —
    including a 200 with no refresh token, which is a real Google behaviour on
    re-authorisation and would otherwise store an empty secret that looks
    connected.
    """
    client_id, client_secret = client_credentials()
    body = _post(
        _endpoints().token,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if not body.get("refresh_token"):
        raise OAuthError(
            "Google returned no refresh token. Reconnect and approve offline "
            "access when prompted."
        )
    return body


def refresh(*, refresh_token: str) -> dict[str, str]:
    """Exchange a refresh token for a new access token."""
    client_id, client_secret = client_credentials()
    return _post(
        _endpoints().token,
        {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
    )


def revoke(*, refresh_token: str) -> None:
    """Revoke the grant at Google.

    AC-3 says disconnect must actually revoke. Deleting our copy without
    telling Google leaves a live grant on the operator's account that they did
    not ask to keep and cannot see us holding.

    A grant Google has already forgotten answers 400; that is success from
    here — the goal state is "no live grant", and it is reached.
    """
    try:
        response = requests.post(
            _endpoints().revoke,
            data={"token": refresh_token},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise OAuthError(f"Could not reach Google to revoke: {type(exc).__name__}")

    if response.status_code == 400:
        logger.info("revoke returned 400; the grant was already gone")
        return
    if not response.ok:
        raise OAuthError(f"Google refused the revocation ({response.status_code})")


def _post(url: str, data: dict[str, str]) -> dict[str, str]:
    """POST a form and parse JSON, without ever logging the payload.

    ``data`` carries the client secret and, on refresh, the refresh token. It
    is never logged, and neither is the response body — an access token is as
    sensitive in a log line as it is anywhere else. Only the status and the
    error *code* Google returns are recorded.
    """
    try:
        response = requests.post(url, data=data, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise OAuthError(f"Could not reach Google: {type(exc).__name__}")

    try:
        body = response.json()
    except ValueError:
        raise OAuthError(
            f"Google returned a non-JSON response ({response.status_code})"
        )

    if not response.ok or not isinstance(body, dict):
        # Google's own error code is safe to surface and is what an operator
        # or an on-call engineer actually needs — "invalid_grant" means
        # reconnect, "invalid_client" means the deployment is misconfigured.
        code = body.get("error") if isinstance(body, dict) else "unknown"
        logger.warning("google oauth failed: %s (%s)", code, response.status_code)
        raise OAuthError(f"Google rejected the request: {code}")

    return body
