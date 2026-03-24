"""
RouterNode — Intent routing for auto-detect mode.

When a job is submitted without an explicit manifest, the RouterNode
uses keyword matching on the input_prompt to select the best pipeline
from available_manifests.

Keywords carry different weights — platform names (linkedin, twitter)
score higher than generic verbs (write, blog) so that "write a blog
and post it in LinkedIn" routes to social-promotion, not blog-authoring.
"""

from app.nodes.base import BaseNode
from app.state.schema import AgentState

# ── Simple suffix-stripping stemmer (no external deps) ──

_SUFFIX_RULES = [
    ("izing", "iz"),
    ("ising", "is"),
    ("ating", "ate"),
    ("ying", "y"),
    ("ting", "t"),
    ("ning", "n"),
    ("ing", ""),
    ("ies", "y"),
    ("ers", "er"),
    ("ors", "or"),
    ("ments", "ment"),
    ("ness", ""),
    ("ses", "s"),
    ("ions", "ion"),
    ("s", ""),
]


def _stem(word: str) -> str:
    """Reduce a word to its approximate root via suffix stripping."""
    if len(word) <= 3:
        return word
    for suffix, replacement in _SUFFIX_RULES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[: -len(suffix)] + replacement
    return word


# Weighted keyword map: each entry is (keyword, weight).
# Higher weight = stronger signal for that pipeline.
KEYWORD_MAP: dict[str, list[tuple[str, int]]] = {
    "social-promotion": [
        # Platform names — strong signal (weight 3)
        ("linkedin", 3),
        ("twitter", 3),
        ("facebook", 3),
        ("instagram", 3),
        # Phrases (weight 2)
        ("post to linkedin", 2),
        ("post in linkedin", 2),
        ("post on linkedin", 2),
        ("post it in linkedin", 2),
        ("post it on linkedin", 2),
        ("post it to linkedin", 2),
        ("post to twitter", 2),
        ("post on twitter", 2),
        ("share on", 2),
        ("share in", 2),
        ("promote on", 2),
        ("tweet about", 2),
        ("tweet", 2),
        ("linkedin post", 2),
        ("facebook post", 2),
        ("schedule post", 2),
        ("scheduled task", 2),
        ("schedule it", 2),
        # Generic (weight 1)
        ("social", 1),
        ("promote", 1),
        ("social media", 1),
        ("schedule", 1),
        ("scheduled", 1),
        ("post", 1),
    ],
    "social-post": [
        ("post on", 1),
        ("schedule post", 1),
        ("publish to", 1),
    ],
    "blog-authoring": [
        ("write a blog", 3),
        ("write an article", 3),
        ("blog", 1),
        ("write", 1),
        ("author", 1),
        ("article", 1),
        ("publish", 1),
    ],
    "iso-brand-equity": [
        ("brand equity", 3),
        ("brand valuation", 3),
        ("valuation", 2),
        ("iso", 1),
        ("royalty", 1),
        ("10668", 1),
    ],
    "competitor-audit": [
        ("brand audit", 3),
        ("brand gap", 3),
        ("iso benchmark", 2),
        ("audit", 1),
    ],
    "competitor-intelligence": [
        ("competitive analysis", 3),
        ("competitive landscape", 3),
        ("competitor profiling", 3),
        ("swot analysis", 3),
        ("competitive benchmarking", 3),
        ("positioning gap", 3),
        ("competitor", 2),
        ("competitors", 2),
        ("competitive", 2),
        ("swot", 2),
        ("benchmarking", 2),
        ("benchmark", 2),
        ("positioning", 1),
    ],
    "content-strategy": [
        ("content strategy", 3),
        ("content", 1),
        ("strategy", 1),
        ("calendar", 1),
        ("editorial", 1),
    ],
    "market-research": [
        # Market sizing — strong signal (weight 3)
        ("market size", 3),
        ("market sizing", 3),
        ("tam sam som", 3),
        ("total addressable market", 3),
        ("serviceable addressable market", 3),
        ("market opportunity", 3),
        ("market research", 3),
        # Domain phrases — moderate signal (weight 2)
        ("industry trends", 2),
        ("market analysis", 2),
        ("growth potential", 2),
        ("addressable market", 2),
        ("economic indicators", 2),
        ("market forecast", 2),
        ("market potential", 2),
        ("market outlook", 2),
        ("market growth", 2),
        ("tam", 2),
        ("sam", 2),
        ("som", 2),
        # Generic — weak signal (weight 1)
        ("market", 1),
        ("sizing", 1),
        ("trends", 1),
        ("landscape", 1),
        ("forecast", 1),
    ],
    "audience-persona": [
        # Persona-specific — strong signal (weight 3)
        ("buyer persona", 3),
        ("buyer personas", 3),
        ("target audience", 3),
        ("customer persona", 3),
        ("audience persona", 3),
        ("customer segmentation", 3),
        ("buying journey", 3),
        ("customer profile", 3),
        # Domain phrases — moderate signal (weight 2)
        ("audience research", 2),
        ("audience analysis", 2),
        ("demographics", 2),
        ("psychographics", 2),
        ("customer segments", 2),
        ("ideal customer", 2),
        ("audience segments", 2),
        ("media habits", 2),
        ("pain points", 2),
        # Generic — weak signal (weight 1)
        ("persona", 1),
        ("audience", 1),
        ("buyer", 1),
        ("demographic", 1),
    ],
    "audience-persona-discovery": [
        ("full audience discovery", 3),
        ("audience discovery pipeline", 3),
        ("market research and personas", 3),
    ],
    "brand-discovery-full": [
        # Strong signals (weight 3)
        ("trend analysis", 3),
        ("cultural trends", 3),
        ("cultural insights", 3),
        ("brand discovery", 3),
        ("full brand analysis", 3),
        ("trend monitoring", 3),
        ("emerging trends", 3),
        ("viral trends", 3),
        ("generational trends", 3),
        # Moderate signals (weight 2)
        ("social media trends", 2),
        ("cultural shift", 2),
        ("brand relevance", 2),
        ("trend report", 2),
        ("what is trending", 2),
        ("emerging slang", 2),
        ("gen z trends", 2),
        ("millennial trends", 2),
        ("viral content", 2),
        ("meme culture", 2),
        # Weak signals (weight 1)
        ("trending", 1),
        ("culture", 1),
        ("viral", 1),
        ("relevance", 1),
        ("zeitgeist", 1),
    ],
    "trend-cultural-insights": [
        ("cultural trends", 3),
        ("trend analysis", 3),
        ("social media trends", 2),
        ("viral trends", 2),
        ("what is trending", 2),
        ("trending", 1),
        ("culture", 1),
    ],
    "brand-strategy-positioning": [
        # Strong signal (weight 3)
        ("brand positioning", 3),
        ("market positioning", 3),
        ("positioning strategy", 3),
        ("value proposition", 3),
        ("unique value proposition", 3),
        ("uvp", 3),
        ("differentiation strategy", 3),
        ("competitive positioning", 3),
        # Moderate signal (weight 2)
        ("perceptual map", 2),
        ("positioning statement", 2),
        ("brand differentiation", 2),
        ("market position", 2),
        ("value prop canvas", 2),
        ("competitive advantage", 2),
        ("brand strategy", 2),
        # Weak signal (weight 1)
        ("positioning", 1),
        ("differentiation", 1),
        ("unique selling", 1),
        ("usp", 1),
    ],
    "brand-strategy-architecture": [
        # Strong signal (weight 3) — unambiguous intent
        ("brand architecture", 3),
        ("brand hierarchy", 3),
        ("brand structure", 3),
        ("sub-brand strategy", 3),
        ("branded house", 3),
        ("house of brands", 3),
        ("portfolio strategy", 3),
        ("brand portfolio", 3),
        # Medium signal (weight 2) — domain-specific
        ("product line structure", 2),
        ("naming hierarchy", 2),
        ("endorsed brand", 2),
        ("brand relationship", 2),
        ("master brand", 2),
        ("sub-brand", 2),
        # Weak signal (weight 1) — generic terms, need context
        ("architecture", 1),
        ("portfolio", 1),
        ("hierarchy", 1),
    ],
    "brand-analysis": [
        ("brand", 1),
        ("analysis", 1),
    ],
    "odoo-erp-operations": [
        # Odoo-specific — strong signal (weight 3)
        ("odoo", 3),
        ("sales order", 3),
        ("purchase order", 3),
        ("bill of materials", 3),
        ("production order", 3),
        # ERP domain — moderate signal (weight 2)
        ("erp", 2),
        ("inventory", 2),
        ("invoice", 2),
        ("warehouse", 2),
        ("stock level", 2),
        ("payroll", 2),
        ("procurement", 2),
        ("quotation", 2),
        ("leave request", 2),
        ("vendor bill", 2),
        ("stock transfer", 2),
        ("timesheet", 2),
        # Surveys — moderate signal (weight 2)
        ("survey", 2),
        ("questionnaire", 2),
        ("feedback form", 2),
        ("survey response", 2),
        # Email marketing — strong signal (weight 3)
        ("email marketing", 3),
        ("email campaign", 3),
        ("mailing list", 2),
        ("mass mailing", 2),
        ("newsletter", 2),
        ("mailing", 2),
        ("campaign", 1),
        # Generic ERP — weak signal (weight 1)
        ("accounting", 1),
        ("employee", 1),
        ("manufacturing", 1),
        ("stock", 1),
    ],
    "general-chat": [
        ("document", 2),
        ("explain", 2),
        ("summarize", 2),
        ("file", 1),
        ("upload", 1),
        ("pdf", 1),
        ("summary", 1),
        ("what does", 1),
        ("tell me about", 1),
        ("find", 1),
        ("search", 1),
        ("look up", 1),
    ],
    "rag-blog-social": [
        # RAG signals — high weight so this only wins when RAG is present
        ("vertex store", 5),
        ("vertedx store", 5),
        ("rag store", 5),
        ("knowledge base", 4),
        ("from my documents", 4),
        ("from the document", 4),
        ("reviewing the", 3),
        ("review the", 3),
        ("uploaded document", 3),
        # Social signals — break tie vs rag-blog-authoring when social present
        ("linkedin", 2),
        ("twitter", 2),
        ("facebook", 2),
        ("instagram", 2),
        ("schedule", 1),
        ("post", 1),
    ],
    "rag-blog-authoring": [
        # RAG signals — high weight so this only wins when RAG is present
        ("vertex store", 5),
        ("vertedx store", 5),
        ("rag store", 5),
        ("knowledge base", 4),
        ("from my documents", 4),
        ("from the document", 4),
        ("reviewing the", 3),
        ("review the", 3),
        ("uploaded document", 3),
        # Blog signals — break tie vs rag-blog-social when blog but no social
        ("blog", 1),
        ("write", 1),
        ("article", 1),
        ("author", 1),
    ],
}


def keyword_match(state: AgentState) -> str:
    """Improved keyword matching with stemming, phrase scoring, and RAG boosting.

    Shared by RouterNode and PipelineComposer._keyword_fallback().
    """
    prompt = state.get("input_prompt", "").lower()
    available = state.get("available_manifests") or []
    available_ids = {m["pipeline_id"] for m in available} if available else set()
    ctx = state.get("input_context") or {}

    prompt_words = prompt.split()
    stemmed_words = {_stem(w.strip(",.!?;:'\"")) for w in prompt_words}

    scores: dict[str, int] = {}
    for pipeline_id, keywords in KEYWORD_MAP.items():
        if available_ids and pipeline_id not in available_ids:
            continue
        score = 0
        for kw, weight in keywords:
            if " " in kw:
                # Phrase: exact substring match
                if kw in prompt:
                    score += weight
            else:
                # Single word: token-based match only (avoids substring
                # false positives like "post" matching "compost")
                if _stem(kw) in stemmed_words:
                    score += weight
        scores[pipeline_id] = score

    # Boost RAG pipelines when user has uploaded documents
    if ctx.get("needs_rag"):
        for pid in ("rag-blog-social", "rag-blog-authoring", "general-chat"):
            if pid in scores:
                scores[pid] += 4

    # Default: prefer general-chat if available, else first manifest in order
    if available_ids:
        if "general-chat" in available_ids:
            resolved_id = "general-chat"
        else:
            resolved_id = available[0]["pipeline_id"]
    else:
        resolved_id = "general-chat"
    best_score = 0
    for pid, score in scores.items():
        if score > best_score:
            best_score = score
            resolved_id = pid
    return resolved_id


class RouterNode(BaseNode):
    """Routes to the appropriate pipeline via weighted keyword matching."""

    async def __call__(self, state: AgentState) -> dict:
        resolved_id = keyword_match(state)
        return {"resolved_manifest_id": resolved_id}
