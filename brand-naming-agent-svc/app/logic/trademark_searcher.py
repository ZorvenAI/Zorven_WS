"""SKL-NTA-08: Tavily web search for trademark conflicts."""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TrademarkSearcher:
    """Search for existing trademark conflicts via Tavily web search."""

    async def search(self, name: str) -> dict[str, Any]:
        """Search for trademark conflicts for a given brand name.

        Returns dict with 'clear' (bool), 'conflicts' (list), 'notes' (str).
        """
        if not settings.TAVILY_API_KEY:
            logger.debug(
                "Tavily API key not configured, skipping trademark search for %s",
                name,
            )
            return {
                "clear": None,
                "conflicts": [],
                "notes": "Trademark search unavailable (no API key)",
            }

        query = f'"{name}" trademark registered brand'

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.TAVILY_API_KEY,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 5,
                    },
                )

            if resp.status_code != 200:
                logger.warning(
                    "Tavily search failed for %s: %s", name, resp.status_code
                )
                return {
                    "clear": None,
                    "conflicts": [],
                    "notes": f"Trademark search failed (HTTP {resp.status_code})",
                }

            data = resp.json()
            results = data.get("results", [])

            conflicts = []
            for result in results:
                title = result.get("title", "")
                url = result.get("url", "")
                content = result.get("content", "")

                # Check if the result indicates an existing trademark
                trademark_indicators = [
                    "trademark", "registered", "®", "™",
                    "patent", "intellectual property",
                ]
                if any(
                    ind in (title + content).lower()
                    for ind in trademark_indicators
                ):
                    conflicts.append({
                        "title": title,
                        "url": url,
                        "snippet": content[:200],
                    })

            return {
                "clear": len(conflicts) == 0,
                "conflicts": conflicts,
                "notes": (
                    f"Found {len(conflicts)} potential trademark conflict(s)"
                    if conflicts
                    else "No trademark conflicts found"
                ),
            }

        except Exception as exc:
            logger.warning("Trademark search error for %s: %s", name, exc)
            return {
                "clear": None,
                "conflicts": [],
                "notes": f"Trademark search error: {exc}",
            }
