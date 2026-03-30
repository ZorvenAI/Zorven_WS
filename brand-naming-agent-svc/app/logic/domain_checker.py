"""SKL-NTA-06: DNS lookup for domain availability."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DomainChecker:
    """Check domain name availability via DNS lookup."""

    async def check(
        self, slug: str, tlds: list[str] | None = None
    ) -> dict[str, bool | None]:
        """Check domain availability for given slug across TLDs.

        Returns dict mapping TLD to availability (True = available, False = taken,
        None = check failed).
        """
        if tlds is None:
            from app.core.config import settings
            tlds = [
                t.strip() for t in settings.DOMAIN_CHECK_TLDS.split(",")
                if t.strip()
            ]

        results = {}
        for tld in tlds:
            domain = f"{slug}{tld}"
            results[tld] = await self._check_domain(domain)

        return results

    async def _check_domain(self, domain: str) -> bool | None:
        """Check single domain via DNS lookup.

        Returns True if available (no DNS record), False if taken, None on error.
        """
        try:
            import dns.asyncresolver

            resolver = dns.asyncresolver.Resolver()
            resolver.lifetime = 5.0  # 5 second timeout

            try:
                await resolver.resolve(domain, "A")
                return False  # Domain resolves → taken
            except (dns.asyncresolver.NXDOMAIN, dns.asyncresolver.NoAnswer):
                return True  # No DNS record → likely available
            except dns.asyncresolver.NoNameservers:
                return None  # DNS error
        except ImportError:
            logger.warning("dnspython not installed, skipping DNS check for %s", domain)
            return None
        except asyncio.TimeoutError:
            logger.warning("DNS lookup timeout for %s", domain)
            return None
        except Exception as exc:
            logger.warning("DNS lookup error for %s: %s", domain, exc)
            return None
