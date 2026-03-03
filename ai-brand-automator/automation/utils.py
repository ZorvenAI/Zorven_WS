"""
Utility functions for the automation app.
"""

import re

# Pre-compiled patterns for strip_markdown (used on every scheduled post).
_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\((?:[^()]*|\([^()]*\))*\)")
# Link pattern handles one level of nested parentheses in URLs
# (e.g. Wikipedia: https://en.wikipedia.org/wiki/Function_(mathematics)).
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]*|\([^()]*\))*\)")
_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BOLD_STAR = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
_BOLD_UNDER = re.compile(r"(?<!\w)_{1,3}([^_]+)_{1,3}(?!\w)")
_STRIKE = re.compile(r"~~([^~]+)~~")
_BLOCKQUOTE = re.compile(r"^>\s?", re.MULTILINE)
_HR = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_UL = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
_OL = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
_HTML = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n{3,}")

# Placeholder for inline code spans during processing.
_CODE_PLACEHOLDER = "\x00CODE{}\x00"


def strip_markdown(text: str) -> str:
    """Convert markdown-formatted text to clean plain text for social posts.

    Removes headers, bold/italic markers, links, images, code blocks,
    blockquotes, horizontal rules, and list markers while preserving
    the actual content and paragraph structure.

    Inline code spans (e.g. ``__init__``) are protected from the
    emphasis-stripping pass so their contents are not mangled.

    Used when blog content (authored in markdown) is saved as a
    scheduled social post — social platforms render plain text, not
    markdown, so ``# My Title`` should become ``My Title``.
    """
    if not text:
        return text

    # Remove fenced code blocks (``` ... ```)
    result = _CODE_BLOCK.sub("", text)

    # Protect inline code spans from emphasis stripping: replace them
    # with numbered placeholders, then restore after bold/italic removal.
    code_spans: list[str] = []

    def _save_code(m: re.Match) -> str:
        code_spans.append(m.group(1))
        return _CODE_PLACEHOLDER.format(len(code_spans) - 1)

    result = _INLINE_CODE.sub(_save_code, result)

    # Remove images ![alt](url) → alt text
    result = _IMAGE.sub(r"\1", result)
    # Convert links [text](url) → text
    result = _LINK.sub(r"\1", result)
    # Remove headers (# ... ######)
    result = _HEADER.sub("", result)
    # Remove bold/italic markers (**, *, ___)
    result = _BOLD_STAR.sub(r"\1", result)
    # Underscore emphasis: require word boundaries so identifiers like
    # __init__ are not treated as bold markers.
    result = _BOLD_UNDER.sub(r"\1", result)
    # Remove strikethrough (~~text~~)
    result = _STRIKE.sub(r"\1", result)
    # Remove blockquotes (> ...)
    result = _BLOCKQUOTE.sub("", result)
    # Remove horizontal rules (---, ***, ___)
    result = _HR.sub("", result)
    # Remove unordered list markers (- , * , + )
    result = _UL.sub("", result)
    # Remove ordered list markers (1. , 2. , etc.)
    result = _OL.sub("", result)
    # Remove HTML tags
    result = _HTML.sub("", result)
    # Collapse multiple blank lines into at most two newlines
    result = _BLANK_LINES.sub("\n\n", result)

    # Restore inline code spans (now safe from emphasis stripping)
    for idx, span in enumerate(code_spans):
        result = result.replace(_CODE_PLACEHOLDER.format(idx), span)

    return result.strip()
