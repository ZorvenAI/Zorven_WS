"""
Title generator — generates concise session titles using Gemini Flash.

Falls back to word truncation when the API key is empty or on error.
Supports optional skill_context for dynamic prompt augmentation.
"""

import asyncio
import logging
import re
from typing import Optional

from app.prompts.fallbacks import FALLBACK_TITLE_GENERATION

logger = logging.getLogger(__name__)


class TitleGenerator:
    """Generates concise 3-5 word titles for chat sessions."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        skill_context: str = "",
        prompt_loader: Optional[object] = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.skill_context = skill_context
        self._prompt_loader = prompt_loader
        self._model = None

        if api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(model_name)
                logger.info("Gemini configured for title generation: %s", model_name)
            except Exception as exc:
                logger.warning("Failed to configure Gemini: %s", exc)

    async def generate(self, first_message: str, first_response: str = "") -> str:
        """Generate a concise title from the first chat message."""
        if not self._model:
            return self._fallback_title(first_message)

        try:
            import google.generativeai as genai

            # Sanitize user content to prevent prompt injection
            sanitized_message = self._sanitize_input(first_message[:2000])
            sanitized_response = self._sanitize_input(first_response[:500])

            # Load system instruction from prompt-optimization-svc (or fallback)
            if self._prompt_loader is not None:
                base_instruction = await self._prompt_loader.load(
                    "zorven-titling-session",
                    fallback=FALLBACK_TITLE_GENERATION,
                )
            else:
                base_instruction = FALLBACK_TITLE_GENERATION

            prompt = base_instruction + "\n\n"
            if self.skill_context:
                prompt += f"{self.skill_context}\n\n"
            prompt += f"Input: {sanitized_message}"
            if sanitized_response:
                prompt += f"\n\nAssistant response context: {sanitized_response}"

            config = genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=30,
            )

            # Run synchronous Gemini call in a thread to avoid blocking
            # the async event loop.
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=config,
            )
            title = response.text.strip()
            title = self._clean_title(title)
            if title:
                logger.info("Generated title: '%s'", title)
                return title[:255]

            return self._fallback_title(first_message)

        except Exception as exc:
            logger.warning("Title generation failed: %s", exc)
            return self._fallback_title(first_message)

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Sanitize user-provided text before embedding in the prompt.

        Strips control characters and collapses excessive whitespace to
        reduce prompt injection surface.
        """
        # Remove control characters
        text = re.sub(r"[\x00-\x1f\x7f]", "", text)
        # Collapse whitespace
        text = " ".join(text.split())
        return text

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip quotes, excessive punctuation, and whitespace."""
        # Remove surrounding quotes
        title = title.strip("\"'`")
        # Remove trailing punctuation
        title = re.sub(r"[.!?:;,]+$", "", title)
        # Collapse whitespace
        title = " ".join(title.split())
        return title

    @staticmethod
    def _fallback_title(message: str) -> str:
        """Fallback: first 5 words of the message."""
        words = message.split()[:5]
        return " ".join(words)[:255]
