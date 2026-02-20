"""
Scraper factory — wires search engine, browser engine, and data cleaner.

Configures components based on settings (API keys, timeouts, etc.).
"""

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.scrapers.browser_engine import BrowserEngine
from app.scrapers.data_cleaner import DataCleaner
from app.scrapers.search_engine import SearchEngine


class ScraperFactory:
    """Factory for creating configured scraper components."""

    @staticmethod
    def create(
        redis_manager: RedisManager | None = None,
    ) -> tuple[SearchEngine, BrowserEngine, DataCleaner]:
        """
        Create and return configured scraper components.

        Returns:
            Tuple of (SearchEngine, BrowserEngine, DataCleaner)
        """
        search_engine = SearchEngine(
            tavily_api_key=settings.TAVILY_API_KEY,
            redis_manager=redis_manager,
        )

        browser_engine = BrowserEngine(
            timeout=settings.SCRAPE_TIMEOUT,
            redis_manager=redis_manager,
        )

        data_cleaner = DataCleaner()

        return search_engine, browser_engine, data_cleaner
