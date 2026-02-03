"""
Unit Tests for Rate Limiting.

Tests for SlidingWindowRateLimiter, InMemoryRateLimiter, and ThrottledVertexAIAdapter.
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_index.adapters.rate_limiter import (
    InMemoryRateLimiter,
    RateLimiterConfig,
    SlidingWindowRateLimiter,
)
from rag_index.adapters.throttled_vertex_ai_adapter import ThrottledVertexAIAdapter
from rag_index.adapters.vertex_ai_adapter import VertexAIAdapter
from rag_index.domain.exceptions import RateLimitExceededError
from rag_index.domain.models import RateLimitStatus, SyncAction, SyncEvent, SyncResult


# ============================================================================
# RateLimiterConfig Tests
# ============================================================================


class TestRateLimiterConfig:
    """Tests for RateLimiterConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RateLimiterConfig()
        assert config.limit == 600
        assert config.window_seconds == 60
        assert config.key == "rag_sync_rate"
        assert config.wait_on_limit is True
        assert config.max_wait_seconds == 30

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RateLimiterConfig(
            limit=100,
            window_seconds=30,
            key="custom_key",
            wait_on_limit=False,
            max_wait_seconds=10,
        )
        assert config.limit == 100
        assert config.window_seconds == 30
        assert config.key == "custom_key"
        assert config.wait_on_limit is False
        assert config.max_wait_seconds == 10

    def test_burst_limit_default(self):
        """Test default burst limit is 10% of limit."""
        config = RateLimiterConfig(limit=600)
        assert config.burst_limit == 60

    def test_burst_limit_custom(self):
        """Test custom burst limit."""
        config = RateLimiterConfig(limit=600, burst_limit=100)
        assert config.burst_limit == 100


# ============================================================================
# InMemoryRateLimiter Tests
# ============================================================================


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter."""

    @pytest.fixture
    def limiter(self):
        """Create limiter with small limit for testing."""
        config = RateLimiterConfig(
            limit=5,
            window_seconds=1,
            wait_on_limit=False,
        )
        return InMemoryRateLimiter(config)

    @pytest.fixture
    def limiter_with_wait(self):
        """Create limiter that waits on limit."""
        config = RateLimiterConfig(
            limit=3,
            window_seconds=1,
            wait_on_limit=True,
        )
        return InMemoryRateLimiter(config)

    async def test_acquire_success(self, limiter):
        """Test successful token acquisition."""
        result = await limiter.acquire()
        assert result is True

    async def test_acquire_multiple(self, limiter):
        """Test acquiring multiple tokens."""
        for _ in range(5):
            result = await limiter.acquire()
            assert result is True

    async def test_acquire_exceeds_limit_no_wait(self, limiter):
        """Test rate limit exceeded without waiting."""
        # Exhaust the limit
        for _ in range(5):
            await limiter.acquire()

        # Next request should raise
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire()

        assert exc_info.value.current_count == 5
        assert exc_info.value.limit == 5

    async def test_acquire_with_count(self, limiter):
        """Test acquiring multiple tokens at once."""
        result = await limiter.acquire(count=3)
        assert result is True

        status = await limiter.get_status()
        assert status.current_count == 3

    async def test_get_status(self, limiter):
        """Test getting rate limit status."""
        await limiter.acquire()
        await limiter.acquire()

        status = await limiter.get_status()
        assert status.current_count == 2
        assert status.limit == 5
        assert status.remaining == 3

    async def test_get_remaining(self, limiter):
        """Test getting remaining count."""
        await limiter.acquire()
        remaining = await limiter.get_remaining()
        assert remaining == 4

    async def test_is_limited_false(self, limiter):
        """Test is_limited returns False when not limited."""
        result = await limiter.is_limited()
        assert result is False

    async def test_is_limited_true(self, limiter):
        """Test is_limited returns True when limited."""
        for _ in range(5):
            await limiter.acquire()

        result = await limiter.is_limited()
        assert result is True

    async def test_window_reset(self, limiter):
        """Test counter resets after window expires."""
        # Exhaust the limit
        for _ in range(5):
            await limiter.acquire()

        # Wait for window to reset
        await asyncio.sleep(1.1)

        # Should be able to acquire again
        result = await limiter.acquire()
        assert result is True

        status = await limiter.get_status()
        assert status.current_count == 1

    async def test_acquire_waits_on_limit(self, limiter_with_wait):
        """Test acquiring waits when limited."""
        # Exhaust the limit
        for _ in range(3):
            await limiter_with_wait.acquire()

        # Next request should wait and succeed after window reset
        start = time.time()
        result = await limiter_with_wait.acquire()
        elapsed = time.time() - start

        assert result is True
        assert elapsed >= 0.9  # Should have waited for window reset


# ============================================================================
# SlidingWindowRateLimiter Tests
# ============================================================================


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis port."""
        redis = AsyncMock()
        redis.check_rate_limit = AsyncMock(
            return_value=RateLimitStatus(
                current_count=0,
                limit=600,
                remaining=600,
            )
        )
        redis.increment_rate_counter = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def limiter(self, mock_redis):
        """Create limiter with mocked Redis."""
        config = RateLimiterConfig(
            limit=600,
            window_seconds=60,
            wait_on_limit=False,
        )
        return SlidingWindowRateLimiter(mock_redis, config)

    async def test_acquire_success(self, limiter, mock_redis):
        """Test successful token acquisition."""
        result = await limiter.acquire()

        assert result is True
        mock_redis.increment_rate_counter.assert_called_once()

    async def test_acquire_checks_rate_limit(self, limiter, mock_redis):
        """Test that acquire checks rate limit first."""
        await limiter.acquire()

        mock_redis.check_rate_limit.assert_called_once()

    async def test_acquire_rate_limited_no_wait(self, limiter, mock_redis):
        """Test rate limit exceeded without waiting."""
        mock_redis.check_rate_limit.return_value = RateLimitStatus(
            current_count=600,
            limit=600,
            remaining=0,
        )

        with pytest.raises(RateLimitExceededError):
            await limiter.acquire()

        # Should not increment when rate limited
        mock_redis.increment_rate_counter.assert_not_called()

    async def test_get_status(self, limiter, mock_redis):
        """Test getting rate limit status."""
        status = await limiter.get_status()

        assert status.remaining == 600
        mock_redis.check_rate_limit.assert_called_once()

    async def test_get_remaining(self, limiter, mock_redis):
        """Test getting remaining count."""
        remaining = await limiter.get_remaining()

        assert remaining == 600

    async def test_is_limited_false(self, limiter, mock_redis):
        """Test is_limited returns False."""
        result = await limiter.is_limited()

        assert result is False

    async def test_is_limited_true(self, limiter, mock_redis):
        """Test is_limited returns True when at limit."""
        mock_redis.check_rate_limit.return_value = RateLimitStatus(
            current_count=600,
            limit=600,
            remaining=0,
        )

        result = await limiter.is_limited()

        assert result is True


class TestSlidingWindowRateLimiterWithWait:
    """Tests for SlidingWindowRateLimiter wait behavior."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis port with changing status."""
        redis = AsyncMock()
        call_count = 0

        async def mock_check(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return RateLimitStatus(current_count=600, limit=600, remaining=0)
            return RateLimitStatus(current_count=0, limit=600, remaining=600)

        redis.check_rate_limit = AsyncMock(side_effect=mock_check)
        redis.increment_rate_counter = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def limiter(self, mock_redis):
        """Create limiter that waits on limit."""
        config = RateLimiterConfig(
            limit=600,
            window_seconds=60,
            wait_on_limit=True,
            max_wait_seconds=2,
        )
        return SlidingWindowRateLimiter(mock_redis, config)

    async def test_acquire_waits_for_capacity(self, limiter, mock_redis):
        """Test that acquire waits when rate limited."""
        result = await limiter.acquire()

        assert result is True
        # Should have checked rate limit at least twice
        assert mock_redis.check_rate_limit.call_count >= 2


# ============================================================================
# ThrottledVertexAIAdapter Tests
# ============================================================================


class TestThrottledVertexAIAdapter:
    """Tests for ThrottledVertexAIAdapter."""

    @pytest.fixture
    def mock_vertex_adapter(self):
        """Create mock Vertex AI adapter."""
        adapter = AsyncMock(spec=VertexAIAdapter)
        adapter.upsert_document = AsyncMock(
            return_value=SyncResult(
                event_id=uuid.uuid4(),
                trace_id=str(uuid.uuid4()),
                status="COMPLETED",
            )
        )
        adapter.delete_document = AsyncMock(
            return_value=SyncResult(
                event_id=uuid.uuid4(),
                trace_id=str(uuid.uuid4()),
                status="COMPLETED",
            )
        )
        adapter.get_document = AsyncMock(return_value={"id": "doc-123"})
        adapter.check_connection = AsyncMock(return_value=True)
        adapter.get_data_store_path = MagicMock(return_value="path/to/store")
        return adapter

    @pytest.fixture
    def throttled_adapter(self, mock_vertex_adapter):
        """Create throttled adapter with in-memory limiter."""
        return ThrottledVertexAIAdapter(
            vertex_adapter=mock_vertex_adapter,
            use_in_memory_limiter=True,
            rate_limit=5,
            rate_window_seconds=1,
            wait_on_limit=False,
        )

    @pytest.fixture
    def sample_event(self):
        """Create sample sync event."""
        return SyncEvent(
            trace_id="trace-123",
            tenant_id="tenant-456",
            file_id="file-789",
            action=SyncAction.UPSERT,
        )

    async def test_upsert_document_success(
        self,
        throttled_adapter,
        mock_vertex_adapter,
        sample_event,
    ):
        """Test successful upsert with rate limiting."""
        result = await throttled_adapter.upsert_document(
            sample_event,
            {"content": "test"},
        )

        assert result.status == "COMPLETED"
        mock_vertex_adapter.upsert_document.assert_called_once()

    async def test_upsert_document_rate_limited(
        self,
        throttled_adapter,
        mock_vertex_adapter,
        sample_event,
    ):
        """Test upsert fails when rate limited."""
        # Exhaust rate limit
        for _ in range(5):
            await throttled_adapter.upsert_document(sample_event, {"c": "t"})

        with pytest.raises(RateLimitExceededError):
            await throttled_adapter.upsert_document(sample_event, {"c": "t"})

    async def test_delete_document_success(
        self,
        throttled_adapter,
        mock_vertex_adapter,
        sample_event,
    ):
        """Test successful delete with rate limiting."""
        result = await throttled_adapter.delete_document(sample_event)

        assert result.status == "COMPLETED"
        mock_vertex_adapter.delete_document.assert_called_once()

    async def test_delete_document_rate_limited(
        self,
        throttled_adapter,
        mock_vertex_adapter,
        sample_event,
    ):
        """Test delete fails when rate limited."""
        # Exhaust rate limit
        for _ in range(5):
            await throttled_adapter.delete_document(sample_event)

        with pytest.raises(RateLimitExceededError):
            await throttled_adapter.delete_document(sample_event)

    async def test_get_document_success(
        self,
        throttled_adapter,
        mock_vertex_adapter,
    ):
        """Test successful get_document with rate limiting."""
        doc = await throttled_adapter.get_document("doc-123", "tenant-456")

        assert doc is not None
        mock_vertex_adapter.get_document.assert_called_once()

    async def test_check_connection_no_rate_limit(
        self,
        throttled_adapter,
        mock_vertex_adapter,
    ):
        """Test check_connection doesn't consume rate limit."""
        # Exhaust rate limit
        sample_event = SyncEvent(
            trace_id="t",
            tenant_id="t",
            file_id="f",
            action=SyncAction.UPSERT,
        )
        for _ in range(5):
            await throttled_adapter.upsert_document(sample_event, {"c": "t"})

        # check_connection should still work
        result = await throttled_adapter.check_connection()
        assert result is True

    async def test_get_data_store_path(
        self,
        throttled_adapter,
        mock_vertex_adapter,
    ):
        """Test get_data_store_path delegates correctly."""
        _ = throttled_adapter.get_data_store_path("tenant-123")

        mock_vertex_adapter.get_data_store_path.assert_called_with("tenant-123")

    async def test_get_rate_limit_status(self, throttled_adapter):
        """Test getting rate limit status."""
        status = await throttled_adapter.get_rate_limit_status()

        assert status.limit == 5
        assert status.remaining >= 0

    async def test_get_remaining_requests(self, throttled_adapter, sample_event):
        """Test getting remaining requests."""
        await throttled_adapter.upsert_document(sample_event, {"c": "t"})

        remaining = await throttled_adapter.get_remaining_requests()
        assert remaining == 4

    async def test_is_rate_limited_false(self, throttled_adapter):
        """Test is_rate_limited returns False."""
        result = await throttled_adapter.is_rate_limited()
        assert result is False

    async def test_is_rate_limited_true(self, throttled_adapter, sample_event):
        """Test is_rate_limited returns True when limited."""
        for _ in range(5):
            await throttled_adapter.upsert_document(sample_event, {"c": "t"})

        result = await throttled_adapter.is_rate_limited()
        assert result is True


class TestThrottledVertexAIAdapterWithRedis:
    """Tests for ThrottledVertexAIAdapter with Redis-based limiter."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis port."""
        redis = AsyncMock()
        redis.check_rate_limit = AsyncMock(
            return_value=RateLimitStatus(
                current_count=0,
                limit=600,
                remaining=600,
            )
        )
        redis.increment_rate_counter = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_vertex_adapter(self):
        """Create mock Vertex AI adapter."""
        adapter = AsyncMock(spec=VertexAIAdapter)
        adapter.upsert_document = AsyncMock(
            return_value=SyncResult(
                event_id=uuid.uuid4(),
                trace_id=str(uuid.uuid4()),
                status="COMPLETED",
            )
        )
        return adapter

    @pytest.fixture
    def throttled_adapter(self, mock_vertex_adapter, mock_redis):
        """Create throttled adapter with Redis limiter."""
        return ThrottledVertexAIAdapter(
            vertex_adapter=mock_vertex_adapter,
            redis_port=mock_redis,
            rate_limit=600,
        )

    @pytest.fixture
    def sample_event(self):
        """Create sample sync event."""
        return SyncEvent(
            trace_id="trace-123",
            tenant_id="tenant-456",
            file_id="file-789",
            action=SyncAction.UPSERT,
        )

    async def test_uses_redis_limiter(
        self,
        throttled_adapter,
        mock_redis,
        sample_event,
    ):
        """Test that Redis-based limiter is used."""
        await throttled_adapter.upsert_document(sample_event, {"c": "t"})

        mock_redis.check_rate_limit.assert_called()
        mock_redis.increment_rate_counter.assert_called()
