"""
API routes for chat-titling-worker.

Endpoints:
  GET /health — Health check (no auth)
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.messaging.kafka_consumer import TitlingConsumer

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level consumer — initialized in main.py lifespan
consumer: Optional[TitlingConsumer] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    kafka_connected: bool = False


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        kafka_connected=consumer.is_connected if consumer else False,
    )
