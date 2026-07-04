"""Hypothesis property tests for prompt cache key generation (US-004)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.cache.prompt_cache import PromptCacheManager


_names = st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"))
_tenant_ids = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_")))


class TestPromptKeyProperties:

    @given(name=_names)
    @hyp_settings(max_examples=50)
    def test_production_key_starts_with_prompt(self, name):
        key = PromptCacheManager._prompt_key(name)
        assert key.startswith("prompt:")

    @given(name=_names)
    @hyp_settings(max_examples=50)
    def test_production_key_ends_with_production(self, name):
        key = PromptCacheManager._prompt_key(name)
        assert key.endswith(":production")

    @given(name=_names, tenant_id=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"))
    @hyp_settings(max_examples=50)
    def test_tenant_key_contains_tenant_id(self, name, tenant_id):
        key = PromptCacheManager._prompt_key(name, tenant_id)
        assert tenant_id in key
        assert ":tenant:" in key

    @given(name=_names)
    @hyp_settings(max_examples=50)
    def test_production_and_tenant_keys_differ(self, name):
        prod = PromptCacheManager._prompt_key(name)
        tenant = PromptCacheManager._prompt_key(name, "t-1")
        assert prod != tenant

    @given(name=_names)
    @hyp_settings(max_examples=30)
    def test_lock_key_starts_with_optimization_lock(self, name):
        key = PromptCacheManager._lock_key(name)
        assert key.startswith("prompt:optimization:lock:")
        assert name in key

    @given(name=_names)
    @hyp_settings(max_examples=30)
    def test_progress_key_starts_with_optimization_progress(self, name):
        key = PromptCacheManager._progress_key(name)
        assert key.startswith("prompt:optimization:progress:")
        assert name in key
