"""SKL-NTA-07: HTTP HEAD for social handle availability."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Platform URL templates — {handle} is replaced with the slug
PLATFORM_URLS = {
    "twitter": "https://x.com/{handle}",
    "instagram": "https://www.instagram.com/{handle}/",
    "linkedin": "https://www.linkedin.com/company/{handle}/",
}


class SocialHandleChecker:
    """Check social media handle availability via HTTP."""

    async def check(
        self, slug: str, platforms: list[str] | None = None
    ) -> dict[str, bool | None]:
        """Check social handle availability across platforms.

        Returns dict mapping platform to availability (True = available,
        False = taken, None = check failed).
        """
        if platforms is None:
            from app.core.config import settings
            platforms = [
                p.strip() for p in settings.SOCIAL_PLATFORMS.split(",")
                if p.strip()
            ]

        results = {}
        for platform in platforms:
            results[platform] = await self._check_handle(platform, slug)

        return results

    async def _check_handle(
        self, platform: str, slug: str
    ) -> bool | None:
        """Check single social handle via HTTP HEAD.

        Returns True if available (404), False if taken (200), None on error.
        """
        url_template = PLATFORM_URLS.get(platform)
        if not url_template:
            return None

        url = url_template.format(handle=slug)
        try:
            async with httpx.AsyncClient(
                timeout=5,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; BrandCheck/1.0)"
                    ),
                },
            ) as client:
                resp = await client.head(url)

            if resp.status_code == 404:
                return True  # Handle available
            elif resp.status_code == 200:
                return False  # Handle taken
            else:
                # Ambiguous — some platforms return 302, 403, etc.
                return None
        except httpx.TimeoutException:
            logger.warning("Social check timeout for %s/%s", platform, slug)
            return None
        except Exception as exc:
            logger.warning("Social check error for %s/%s: %s", platform, slug, exc)
            return None
