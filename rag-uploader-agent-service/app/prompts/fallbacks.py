"""Fallback prompts for RAG Uploader -- used when MLflow and Redis are both unreachable.

These are verbatim copies of the prompts currently used in production.
They serve as the last-resort fallback when both Redis cache and MLflow are
unavailable. The prompt-optimization-svc (MLflow) is the primary source of
truth; these fallbacks ensure zero-downtime degradation.
"""

# Verbatim copy of the smart title prompt from smart_titler.py
FALLBACK_SMART_TITLE = (
    "Generate a short, professional filename (3-5 words, no extension) "
    "for this document. Return ONLY the filename, nothing else."
)

# Map catalog names -> fallback constants for programmatic lookup
FALLBACK_MAP = {
    "zorven-rag-smart-title": FALLBACK_SMART_TITLE,
}
