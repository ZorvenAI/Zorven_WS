"""Mints real tenant JWTs for the spike.

Deliberately matches the monorepo's Kong configuration so the same token is
accepted by both the gateway and the service:

``deployment/docker/kong/kong.yaml``::

    jwt_secrets:
      - consumer: django-backend
        key: ai-brand-automator      # matched against the iss claim
        algorithm: HS256
        secret: "${JWT_SECRET_KEY}"

and the ``jwt`` plugin is configured with ``key_claim_name: iss``, so the
``iss`` claim must equal the key above or Kong cannot find the secret.
"""

from __future__ import annotations

import datetime as dt

import jwt

DEFAULT_ISSUER = "ai-brand-automator"


def mint(
    secret: str,
    *,
    tenant_id: str = "tenant-spike",
    subject: str = "operator@zorven.ai",
    issuer: str = DEFAULT_ISSUER,
    role: str = "Admin",
    lifetime_seconds: int = 3600,
    now: dt.datetime | None = None,
) -> str:
    """Sign a valid tenant JWT."""
    issued = now or dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "tenant_id": tenant_id,
            "role": role,
            "iat": issued,
            "exp": issued + dt.timedelta(seconds=lifetime_seconds),
        },
        secret,
        algorithm="HS256",
    )


def mint_expired(secret: str, **kwargs) -> str:
    """Sign a structurally valid token that expired an hour ago."""
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    return mint(secret, lifetime_seconds=3600, now=past, **kwargs)


def mint_wrong_secret(**kwargs) -> str:
    """Sign with the wrong key — verifies as a forgery, not as expired."""
    return mint("not-the-real-secret", **kwargs)


def mint_tenantless(secret: str, issuer: str = DEFAULT_ISSUER) -> str:
    """A token that verifies but carries no tenant claim.

    A socket that opens on this token is a spike failure, per A-02's notes.
    """
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": "operator@zorven.ai",
            "iat": now,
            "exp": now + dt.timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
