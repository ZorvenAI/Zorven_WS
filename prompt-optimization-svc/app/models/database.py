"""Async database engine and session factory."""

import logging
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# libpq connection parameters that asyncpg's connect() does not accept.
# SQLAlchemy forwards unrecognised query params straight through, so leaving
# any of these in the URL raises
#   TypeError: connect() got an unexpected keyword argument 'sslmode'
_LIBPQ_ONLY_PARAMS = frozenset(
    {
        "sslmode",
        "channel_binding",
        "gssencmode",
        "options",
        "target_session_attrs",
        "sslcert",
        "sslkey",
        "sslrootcert",
        "sslcrl",
        "connect_timeout",
    }
)

# sslmode values that mean "do not use TLS".
_SSL_DISABLED_MODES = frozenset({"disable", "allow"})


def get_async_url(url: str) -> str:
    """Convert a sync PostgreSQL URL to async (asyncpg).

    Beyond swapping the driver, libpq-only query parameters must be removed:
    asyncpg rejects them, and SQLAlchemy passes unknown params through to
    ``asyncpg.connect()``. Managed Postgres providers append them as a matter
    of course — Neon URLs always carry
    ``?sslmode=require&channel_binding=require`` — so a URL that works with
    psycopg2 (and therefore with Alembic) breaks the async engine.

    TLS intent is preserved by translating ``sslmode`` into asyncpg's own
    ``ssl`` parameter, which SQLAlchemy's asyncpg dialect understands.
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    if not parts.query:
        return url

    kept: list[tuple[str, str]] = []
    ssl_required = False

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            ssl_required = value.lower() not in _SSL_DISABLED_MODES
            continue
        if key in _LIBPQ_ONLY_PARAMS:
            continue
        kept.append((key, value))

    if ssl_required and not any(key == "ssl" for key, _ in kept):
        kept.append(("ssl", "require"))

    return urlunsplit(parts._replace(query=urlencode(kept)))


engine = create_async_engine(
    get_async_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    echo=False,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session
