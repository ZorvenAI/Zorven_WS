"""
Utility functions for the automation app.
"""

import re


def strip_markdown(text: str) -> str:
    """Convert markdown-formatted text to clean plain text for social posts.

    Removes headers, bold/italic markers, links, images, code blocks,
    blockquotes, horizontal rules, and list markers while preserving
    the actual content and paragraph structure.

    Used when blog content (authored in markdown) is saved as a
    scheduled social post — social platforms render plain text, not
    markdown, so ``# My Title`` should become ``My Title``.
    """
    if not text:
        return text

    # Remove code blocks (``` ... ```)
    result = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code (`code`)
    result = re.sub(r"`([^`]+)`", r"\1", result)
    # Remove images ![alt](url)
    result = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", result)
    # Convert links [text](url) → text
    result = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", result)
    # Remove headers (# ... ######)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    # Remove bold/italic markers (**, __, *, _)
    result = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", result)
    result = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", result)
    # Remove strikethrough (~~text~~)
    result = re.sub(r"~~([^~]+)~~", r"\1", result)
    # Remove blockquotes (> ...)
    result = re.sub(r"^>\s?", "", result, flags=re.MULTILINE)
    # Remove horizontal rules (---, ***, ___)
    result = re.sub(r"^[-*_]{3,}\s*$", "", result, flags=re.MULTILINE)
    # Remove unordered list markers (- , * , + )
    result = re.sub(r"^[\s]*[-*+]\s+", "", result, flags=re.MULTILINE)
    # Remove ordered list markers (1. , 2. , etc.)
    result = re.sub(r"^[\s]*\d+\.\s+", "", result, flags=re.MULTILINE)
    # Remove HTML tags
    result = re.sub(r"<[^>]+>", "", result)
    # Collapse multiple blank lines into at most two newlines
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()
