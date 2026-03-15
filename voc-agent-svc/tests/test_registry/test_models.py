"""Tests for registry domain models."""

import pytest

from app.registry.models import (
    FeedbackItem,
    ReviewFeedback,
    hash_customer_id,
)


@pytest.mark.unit
def test_hash_customer_id_deterministic():
    """Same input produces the same SHA-256 hash."""
    h1 = hash_customer_id(42)
    h2 = hash_customer_id(42)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


@pytest.mark.unit
def test_hash_customer_id_with_salt():
    """Different salt produces a different hash."""
    h1 = hash_customer_id(42, salt="tenant-a")
    h2 = hash_customer_id(42, salt="tenant-b")
    assert h1 != h2
    # Both should be 64 chars
    assert len(h1) == 64
    assert len(h2) == 64


@pytest.mark.unit
def test_feedback_item_defaults():
    """FeedbackItem has expected default values."""
    item = FeedbackItem()
    assert item.feedback_id == ""
    assert item.text == ""
    assert item.sentiment_label == ""
    assert item.sentiment_score == 0.0
    assert item.metadata == {}


@pytest.mark.unit
def test_review_feedback_creation():
    """ReviewFeedback can be created with platform-specific fields."""
    review = ReviewFeedback(
        feedback_id="review-001",
        text="Great product with excellent support",
        platform="G2",
        rating=4.5,
        verified=True,
        review_title="Excellent SaaS Tool",
        pros=["easy to use", "good support"],
        cons=["pricing"],
    )
    assert review.platform == "G2"
    assert review.rating == 4.5
    assert review.verified is True
    assert len(review.pros) == 2
    assert len(review.cons) == 1
    assert review.channel.value == "reviews"
