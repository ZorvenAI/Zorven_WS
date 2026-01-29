"""
Ports layer - Abstract interfaces for external dependencies.

These Abstract Base Classes define the contracts that adapters must implement.
The domain layer depends only on these interfaces, not on concrete implementations.
"""

from .storage_port import StoragePort
from .cache_port import CachePort
from .event_port import EventProducerPort, EventConsumerPort

__all__ = [
    "StoragePort",
    "CachePort",
    "EventProducerPort",
    "EventConsumerPort",
]
