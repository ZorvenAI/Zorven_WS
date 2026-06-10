"""Celery tasks for prompt-optimization-svc."""

from app.tasks.mine_golden_examples import mine_golden_examples
from app.tasks.optimize_wf1_pipeline import optimize_wf1_pipeline
from app.tasks.optimize_wf2_pipeline import optimize_wf2_pipeline
from app.tasks.optimize_wf3_pipeline import (
    optimize_wf3_creative_pipeline,
    optimize_wf3_optimization_loop,
)
from app.tasks.prompt_health_check import prompt_health_check

__all__ = [
    "mine_golden_examples",
    "optimize_wf1_pipeline",
    "optimize_wf2_pipeline",
    "optimize_wf3_creative_pipeline",
    "optimize_wf3_optimization_loop",
    "prompt_health_check",
]
