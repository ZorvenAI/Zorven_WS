"""Tests for Redis cache manager."""

from app.cache.redis_manager import RedisManager


class TestBuildCacheKey:
    def test_same_inputs_same_key(self):
        k1 = RedisManager.build_cache_key("Nike", "", "", "Retail", "large", "global")
        k2 = RedisManager.build_cache_key("Nike", "", "", "Retail", "large", "global")
        assert k1 == k2

    def test_case_insensitive(self):
        k1 = RedisManager.build_cache_key("NIKE", "", "", "retail", "Large", "GLOBAL")
        k2 = RedisManager.build_cache_key("nike", "", "", "Retail", "large", "global")
        assert k1 == k2

    def test_strips_suffixes(self):
        k1 = RedisManager.build_cache_key(
            "Nike, Inc.", "", "", "Retail", "large", "global"
        )
        k2 = RedisManager.build_cache_key("Nike", "", "", "Retail", "large", "global")
        assert k1 == k2

    def test_different_address_different_key(self):
        k1 = RedisManager.build_cache_key(
            "Nike", "Portland", "", "Retail", "large", "global"
        )
        k2 = RedisManager.build_cache_key(
            "Nike", "New York", "", "Retail", "large", "global"
        )
        assert k1 != k2

    def test_different_website_different_key(self):
        k1 = RedisManager.build_cache_key(
            "Nike", "", "nike.com", "Retail", "large", "global"
        )
        k2 = RedisManager.build_cache_key(
            "Nike", "", "nike.co.uk", "Retail", "large", "global"
        )
        assert k1 != k2

    def test_key_prefix(self):
        key = RedisManager.build_cache_key("Test", "", "", "Tech", "small", "local")
        assert key.startswith("equity:result:")
