"""Golden dataset seeder — loads examples into PostgreSQL."""

import hashlib
import json
import logging
from dataclasses import dataclass

from app.datasets.golden_seed import GOLDEN_EXAMPLES

logger = logging.getLogger(__name__)


@dataclass
class SeedResult:
    """Summary of a seeding operation."""

    created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.details is None:
            self.details = []


def _context_hash(input_context: dict) -> str:
    """Generate a stable hash for an input_context dict."""
    raw = json.dumps(input_context, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def seed_golden_datasets(session_factory) -> SeedResult:
    """Seed golden dataset examples into PostgreSQL.

    Idempotent: skips examples that already exist (matched by
    prompt_name + agent_code + context hash).
    """
    from app.models.golden_dataset import GoldenDataset
    from sqlalchemy import select

    result = SeedResult()

    async with session_factory() as session:
        for example in GOLDEN_EXAMPLES:
            try:
                ctx_hash = _context_hash(example.input_context)

                # Check if already exists
                stmt = select(GoldenDataset).where(
                    GoldenDataset.prompt_name == example.prompt_name,
                    GoldenDataset.agent_code == example.agent_code,
                )
                existing = await session.execute(stmt)
                rows = existing.scalars().all()

                # Check context hash match
                already_exists = any(
                    _context_hash(row.input_context or {}) == ctx_hash for row in rows
                )

                if already_exists:
                    result.skipped += 1
                    continue

                row = GoldenDataset(
                    prompt_name=example.prompt_name,
                    agent_code=example.agent_code,
                    input_context=example.input_context,
                    expected_output=example.expected_output,
                    source=example.source,
                    metadata_extra=example.metadata_extra,
                    active=True,
                )
                session.add(row)
                result.created += 1
            except Exception as exc:
                result.errors += 1
                result.details.append(f"ERROR: {example.prompt_name} — {exc}")
                logger.error("Failed to seed %s: %s", example.prompt_name, exc)

        await session.commit()

    logger.info(
        "Golden dataset seeding: %d created, %d skipped, %d errors",
        result.created,
        result.skipped,
        result.errors,
    )
    return result
