"""
Title generator — generates concise session titles using Gemini Flash.

Falls back to word truncation when the API key is empty or on error.
"""

import logging
import re

logger = logging.getLogger(__name__)


class TitleGenerator:
    """Generates concise 3-5 word titles for chat sessions."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._model = None

        if api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(model_name)
                logger.info("Gemini configured for title generation: %s", model_name)
            except Exception as exc:
                logger.warning("Failed to configure Gemini: %s", exc)

    async def generate(
        self, first_message: str, first_response: str = ""
    ) -> str:
        """Generate a concise title from the first chat message."""
        if not self._model:
            return self._fallback_title(first_message)

        try:
            import google.generativeai as genai

            prompt = (
                "You are a session namer. Based on the following user message, "
                "generate a 3 to 5-word title for the chat session. "
                "Do not use punctuation. Do not use quotes. "
                "Example: 'Tesla Q4 Revenue Review'\n\n"
                f"Input: {first_message[:2000]}"
            )
            if first_response:
                prompt += f"\n\nAssistant response context: {first_response[:500]}"

            response = self._model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=30,
                ),
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
