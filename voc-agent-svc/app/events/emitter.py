"""Re-export EventEmitter from catalog for convenience."""

from app.events.catalog import EventEmitter, EventType

__all__ = ["EventEmitter", "EventType"]
