"""
Data cleaner — converts raw HTML to clean Markdown.

Strips scripts, styles, navigation, headers, and footers
before converting to Markdown via markdownify.
"""

import logging
import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger(__name__)

# MIME types considered downloadable (not HTML to scrape)
DOWNLOADABLE_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "application/zip",
    "application/gzip",
}

# Tags to strip before Markdown conversion
STRIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "iframe"]


class DataCleaner:
    """HTML-to-Markdown converter with content stripping."""

    def __init__(self, max_length: int = 50000) -> None:
        self.max_length = max_length

    def clean(self, html: str) -> str:
        """
        Convert HTML to clean Markdown.

        Strips scripts, styles, nav, header, footer elements.
        Truncates to max_length characters.
        """
        if not html or not html.strip():
            return ""

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Remove unwanted tags
            for tag_name in STRIP_TAGS:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

            # Convert to Markdown
            cleaned_html = str(soup)
            if not cleaned_html.strip():
                return ""

            markdown = md(cleaned_html, strip=["img"])

            # Clean up excessive whitespace
            markdown = re.sub(r"\n{3,}", "\n\n", markdown)
            markdown = markdown.strip()

            # Truncate if needed
            if len(markdown) > self.max_length:
                markdown = markdown[: self.max_length]

            return markdown

        except Exception as exc:
            logger.error("Error cleaning HTML: %s", exc)
            return ""

    @staticmethod
    def is_downloadable(url: str, content_type: str) -> bool:
        """
        Check if a URL/content-type indicates a downloadable file.

        Returns True for PDFs, Excel, Word, CSV, and archives.
        """
        # Check MIME type
        base_type = content_type.split(";")[0].strip().lower()
        if base_type in DOWNLOADABLE_TYPES:
            return True

        # Check URL extension as fallback
        url_lower = url.lower().rstrip("/")
        downloadable_extensions = (
            ".pdf",
            ".xlsx",
            ".xls",
            ".docx",
            ".doc",
            ".csv",
            ".zip",
            ".gz",
        )
        return url_lower.endswith(downloadable_extensions)
