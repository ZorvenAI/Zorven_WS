"""ILA intelligence loop scorers."""

from app.scorers.ila.learning_depth import learning_depth
from app.scorers.ila.meta_policy import meta_policy

ILA_SCORERS = [
    learning_depth,
    meta_policy,
]

__all__ = [
    "ILA_SCORERS",
    "learning_depth",
    "meta_policy",
]
