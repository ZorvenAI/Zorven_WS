"""Celery tasks for prompt-optimization-svc."""

from app.tasks.mine_golden_examples import mine_golden_examples

__all__ = ["mine_golden_examples"]
