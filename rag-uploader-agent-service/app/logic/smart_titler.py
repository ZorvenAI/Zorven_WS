"""SmartTitler — generates descriptive filenames for generic uploads.

If the file name is generic (e.g., "upload.pdf", "document1.pdf"), uses
Gemini to generate a professional, descriptive filename from the file
content. Falls back to the original name when Gemini is unavailable.
"""

import asyncio
import logging
import re
from typing import Any

from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)

# Patterns that indicate a generic, non-descriptive filename
_GENERIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^upload\d*\.\w+$",
        r"^document\d*\.\w+$",
        r"^file\d*\.\w+$",
        r"^untitled\d*\.\w+$",
        r"^download\d*\.\w+$",
        r"^image\d*\.\w+$",
        r"^IMG_\d+\.\w+$",
        r"^Screenshot[_\s]?\d*\.\w+$",
        r"^Scan[_\s]?\d*\.\w+$",
        r"^tmp[_\-]?\d*\.\w+$",
        r"^temp[_\-]?\d*\.\w+$",
        r"^attachment\d*\.\w+$",
        r"^[a-f0-9]{8,}\.\w+$",  # hex hash filenames
    ]
]

MAX_FILENAME_LENGTH = 200


class SmartTitler:
    """Generates descriptive filenames for generic uploads."""

    def __init__(self, gemini_model: Any = None) -> None:
        self._model = gemini_model

    async def title(
        self,
        filename: str,
        content_preview: bytes = b"",
        skill_context: str = "",
    ) -> str:
        """Generate a descriptive filename if the current name is generic.

        Args:
            filename: Current filename (e.g., "upload.pdf").
            content_preview: First 500 bytes of file content for LLM context.
            skill_context: Optional skill instructions from orchestrator.

        Returns:
            A slugified, GCS-compatible filename with the original extension.
        """
        if not filename:
            return "unnamed_document"

        # Extract extension
        dot_idx = filename.rfind(".")
        if dot_idx > 0:
            ext = filename[dot_idx:]
            base = filename[:dot_idx]
        else:
            ext = ""
            base = filename

        # If not generic, just slugify and return
        if not self._is_generic(filename):
            return self._slugify(base, ext)

        # Try LLM-based rename
        if self._model is not None:
            try:
                new_name = await self._llm_rename(
                    filename, content_preview, skill_context=skill_context
                )
                if new_name:
                    return self._slugify(new_name, ext)
            except Exception as exc:
                logger.warning("SmartTitler LLM rename failed: %s", exc)

        # Fallback: return original (slugified)
        return self._slugify(base, ext)

    @staticmethod
    def _is_generic(filename: str) -> bool:
        """Check if a filename matches a generic pattern."""
        return any(p.match(filename) for p in _GENERIC_PATTERNS)

    async def _llm_rename(
        self,
        filename: str,
        content_preview: bytes,
        skill_context: str = "",
    ) -> str:
        """Ask Gemini for a descriptive filename based on content."""
        # Try to decode content preview for context
        preview_text = ""
        if content_preview:
            try:
                preview_text = content_preview[:500].decode("utf-8", errors="replace")
            except Exception:
                preview_text = "[binary content]"

        prompt = sanitize_ai_prompt(
            "Generate a short, professional filename (3-5 words, no extension) "
            "for this document. Return ONLY the filename, nothing else.\n\n"
            f"Current filename: {filename}\n"
        )
        if skill_context:
            prompt += f"\n{skill_context}\n\n"
        if preview_text:
            prompt += f"Content preview:\n{preview_text[:500]}\n"

        response = await asyncio.to_thread(
            self._model.generate_content,
            prompt,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 50,
            },
        )

        result = response.text.strip()
        # Remove any extension the LLM might have added
        if "." in result:
            result = result.rsplit(".", 1)[0]
        return result

    @staticmethod
    def _slugify(name: str, ext: str = "") -> str:
        """Convert a name to a GCS-compatible slug.

        - Replaces spaces and special characters with underscores
        - Removes consecutive underscores
        - Strips leading/trailing underscores
        - Enforces max length
        - Appends the original extension
        """
        # Replace spaces and common separators with underscores
        slug = re.sub(r"[\s\-]+", "_", name)
        # Remove anything that isn't alphanumeric or underscore
        slug = re.sub(r"[^a-zA-Z0-9_]", "", slug)
        # Collapse consecutive underscores
        slug = re.sub(r"_+", "_", slug)
        # Strip leading/trailing underscores
        slug = slug.strip("_")

        if not slug:
            slug = "unnamed_document"

        # Enforce max length (leaving room for extension)
        max_base = MAX_FILENAME_LENGTH - len(ext)
        if len(slug) > max_base:
            slug = slug[:max_base].rstrip("_")

        return slug + ext
