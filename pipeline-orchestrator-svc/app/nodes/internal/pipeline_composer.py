"""
PipelineComposer — Dynamic, catalog-driven pipeline composition.

Replaces RouterNode for auto-detect mode. Uses a 3-tier routing chain:

  Tier 1: Enhanced Gemini dynamic composition (context-enriched + retry)
  Tier 2: Gemini manifest classification (lightweight LLM picks 1 of 9)
  Tier 3: Improved keyword matching (stemming, weights, neutral default)

Falls back through the tiers on failure. Adding a new agent requires
only one dict entry in NODE_CATALOG.
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.nodes.internal.router_node import keyword_match
from app.state.schema import AgentState
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)

# ── Node Catalog — single source of truth for available agents ──

NODE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "default_agent",
        "type": "internal",
        "handler": "DefaultAgentNode",
        "description": (
            "RAG specialist: retrieves and analyzes documents from the "
            "user's Vertex AI data store / knowledge base. Use when the "
            "prompt references uploaded documents, the RAG store, vertex "
            "store, knowledge base, or asks to review/summarize a "
            "specific document."
        ),
        "output_key": "default_agent",
    },
    {
        "id": "web_research",
        "type": "external",
        "url": f"{settings.DISCOVERY_AGENT_URL}/v1/search",
        "description": (
            "Web research: searches the internet via Tavily for current "
            "data, statistics, trends, competitor info. Use when the "
            "prompt needs fresh web data, market research, or doesn't "
            "reference uploaded documents."
        ),
        "output_key": "web_research",
        "config": {"focus": "topic_research,statistics,trends"},
    },
    {
        "id": "blog_author",
        "type": "external",
        "url": f"{settings.CONTENT_AGENT_URL}/v1/execute",
        "description": (
            "Blog author: writes SEO-optimized blog posts in markdown. "
            "Needs research input from either web_research or "
            "default_agent. Use when the prompt asks to write, author, "
            "or create a blog post or article."
        ),
        "output_key": "blog_author",
        "config": {"output_format": "markdown"},
    },
    {
        "id": "social_promoter",
        "type": "external",
        "url": f"{settings.SOCIAL_AGENT_URL}/v1/execute",
        "description": (
            "Social media promoter: adapts content for social platforms "
            "and publishes or schedules posts. Use when the prompt "
            "mentions LinkedIn, Twitter, Facebook, Instagram, social "
            "media, posting, sharing, scheduling, or promoting."
        ),
        "output_key": "social_promoter",
        "config": {"platforms": ["linkedin", "twitter"]},
    },
    {
        "id": "valuation_logic",
        "type": "external",
        "url": f"{settings.INTELLIGENCE_AGENT_URL}/v1/iso-calc",
        "description": (
            "ISO 10668 brand valuation using Royalty Relief NPV. Use "
            "when the prompt asks about brand valuation, brand equity, "
            "ISO, royalty, or NPV."
        ),
        "output_key": "valuation_logic",
        "config": {"method": "royalty_relief", "horizon_years": 5},
    },
    {
        "id": "gap_analyzer",
        "type": "external",
        "url": f"{settings.INTELLIGENCE_AGENT_URL}/v1/analyze",
        "description": (
            "Competitive gap analysis. Use when the prompt mentions "
            "competitor analysis, audit, competitive gaps, or market "
            "comparison."
        ),
        "output_key": "gap_analyzer",
        "config": {"analysis_type": "competitive_gap"},
    },
    {
        "id": "rag_uploader",
        "type": "external",
        "url": f"{settings.RAG_UPLOADER_AGENT_URL}/v1/execute",
        "description": (
            "RAG archivist: persists documents and files to the tenant's "
            "long-term Vertex AI knowledge base. Use when the user wants "
            "to save, archive, upload, store, or persist files to their "
            "knowledge base, RAG store, or document library. Also use "
            "when the user says 'remember this' or 'keep this for later'."
        ),
        "output_key": "rag_uploader",
        "config": {},
    },
    # ──────────────────────────────────────────────────────────
    # TO ADD A NEW AGENT: Simply append an entry here.
    # The PipelineComposer will automatically pick it up.
    # ──────────────────────────────────────────────────────────
]

# Fast lookup by node id
NODE_CATALOG_MAP: dict[str, dict[str, Any]] = {n["id"]: n for n in NODE_CATALOG}

# ── Available pipeline manifests for Tier 2 classification ──

_PIPELINE_DESCRIPTIONS: list[dict[str, str]] = [
    {
        "id": "brand-analysis",
        "description": "Full brand analysis: positioning, market, audience insights",
    },
    {
        "id": "blog-authoring",
        "description": "Write SEO-optimized blog posts using web research",
    },
    {
        "id": "social-promotion",
        "description": "Create and publish social media posts (LinkedIn, Twitter, etc.)",
    },
    {
        "id": "iso-brand-equity",
        "description": "ISO 10668 brand valuation using Royalty Relief NPV method",
    },
    {
        "id": "competitor-audit",
        "description": "Competitive gap analysis comparing brand against competitors",
    },
    {
        "id": "content-strategy",
        "description": "Editorial calendar and content strategy planning",
    },
    {
        "id": "general-chat",
        "description": "General Q&A, document analysis, and RAG-based queries",
    },
    {
        "id": "rag-blog-social",
        "description": ("Blog + social posting using RAG documents (not web research)"),
    },
    {
        "id": "rag-blog-authoring",
        "description": "Blog authoring using RAG documents (not web research)",
    },
]

# ── Few-shot examples for Tier 1 ──

_FEW_SHOT_EXAMPLES = """
Examples of prompt → pipeline compositions:
- "Write a blog about Tesla" → [web_research, blog_author, manager]
- "Post about our brand on LinkedIn" → [web_research, blog_author, social_promoter, manager]
- "Calculate brand equity for Nike" → [web_research, valuation_logic, manager]
- "Analyze our competitors in the SaaS market" → [web_research, gap_analyzer, manager]
- "Summarize the document I uploaded" → [default_agent, manager]
- "Write a blog from the uploaded brand study and share on LinkedIn" → [default_agent, blog_author, social_promoter, manager]
""".strip()


def _build_compose_tool(catalog: list[dict]) -> dict:
    """Build the compose_pipeline function-calling tool from the current catalog."""
    valid_ids = [n["id"] for n in catalog]
    return {
        "function_declarations": [
            {
                "name": "compose_pipeline",
                "description": (
                    "Select and order the agent nodes needed to fulfill "
                    "the user's request. Nodes execute sequentially — each "
                    "node receives outputs from all previous nodes. Always "
                    "include 'manager' as the last node. Select the "
                    "minimum set needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": valid_ids + ["manager"],
                            },
                            "description": (
                                "Ordered list of node IDs to execute. "
                                "Must end with 'manager'."
                            ),
                        },
                    },
                    "required": ["node_ids"],
                },
            }
        ]
    }


def _build_classify_tool() -> dict:
    """Build the select_pipeline function-calling tool for Tier 2."""
    valid_ids = [p["id"] for p in _PIPELINE_DESCRIPTIONS]
    return {
        "function_declarations": [
            {
                "name": "select_pipeline",
                "description": (
                    "Select the single best pipeline to handle the user's "
                    "request from the available options."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pipeline_id": {
                            "type": "string",
                            "enum": valid_ids,
                            "description": "The ID of the selected pipeline.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the selection.",
                        },
                    },
                    "required": ["pipeline_id", "reason"],
                },
            }
        ]
    }


def _build_system_prompt(catalog: list[dict]) -> str:
    """Build the base system prompt from the current catalog."""
    node_descriptions = "\n".join(
        f"- **{n['id']}**: {n['description']}" for n in catalog
    )
    return (
        "You are a pipeline orchestrator. Given a user prompt, select "
        "which agent nodes are needed and in what order. Each node's "
        "output flows to the next.\n\n"
        "Available nodes:\n"
        f"{node_descriptions}\n"
        "- **manager**: Terminal node that aggregates all outputs. "
        "Always include last.\n\n"
        "Rules:\n"
        "- Select the MINIMUM set of nodes needed\n"
        "- Nodes that need research input (blog_author, valuation_logic) "
        "must have a research node (default_agent or web_research) "
        "before them\n"
        "- social_promoter should come after content creation "
        "(blog_author)\n"
        "- Always end with manager\n"
        "- For document/RAG queries use default_agent, for web research "
        "use web_research"
    )


def _build_classify_system_prompt(needs_rag: bool = False) -> str:
    """Build the system prompt for Tier 2 LLM classification."""
    pipeline_list = "\n".join(
        f"- **{p['id']}**: {p['description']}" for p in _PIPELINE_DESCRIPTIONS
    )
    rag_hint = ""
    if needs_rag:
        rag_hint = (
            "\n\nIMPORTANT: The user has uploaded documents. Prefer "
            "RAG-based pipelines (rag-blog-social, rag-blog-authoring, "
            "general-chat) over web-research pipelines when the prompt "
            "references their documents."
        )
    return (
        "You are a pipeline router. Given a user prompt, select the "
        "single best pipeline from the options below.\n\n"
        "Available pipelines:\n"
        f"{pipeline_list}\n\n"
        "Routing rules:\n"
        "- Social platform mentions (LinkedIn, Twitter, etc.) → social-promotion\n"
        "- Blog/article writing → blog-authoring\n"
        "- Brand valuation, equity, ISO, royalty → iso-brand-equity\n"
        "- Competitor analysis, competitive gaps → competitor-audit\n"
        "- Content calendar, editorial strategy → content-strategy\n"
        "- Document queries, RAG, summarize → general-chat\n"
        "- RAG + blog + social → rag-blog-social\n"
        "- RAG + blog (no social) → rag-blog-authoring\n"
        "- Brand positioning, market analysis → brand-analysis\n"
        f"- Default for ambiguous queries → general-chat{rag_hint}"
    )


class PipelineComposer:
    """Dynamic pipeline composer using 3-tier routing: Gemini composition,
    LLM classification, and keyword fallback."""

    def __init__(self) -> None:
        self._catalog = NODE_CATALOG
        self._catalog_map = NODE_CATALOG_MAP
        self._tool = _build_compose_tool(self._catalog)
        self._base_system_prompt = _build_system_prompt(self._catalog)
        self._classify_tool = _build_classify_tool()

    async def compose(self, state: AgentState) -> dict[str, Any]:
        """Compose a pipeline for the given state.

        3-tier fallback chain:
          Tier 1: Gemini dynamic composition (context-enriched + retry)
          Tier 2: Gemini manifest classification (picks 1 of 9 pipelines)
          Tier 3: Keyword matching (stemming + RAG boost)

        Returns either:
            {"_composed_manifest": {...}} — Tier 1 succeeded
            {"resolved_manifest_id": "..."} — Tier 2 or 3
        """
        # Tier 1: Enhanced Gemini dynamic composition
        if settings.GOOGLE_API_KEY:
            try:
                node_ids = await self._gemini_compose(state)
                if node_ids:
                    manifest = self._build_manifest(node_ids)
                    logger.info(
                        "Gemini composed pipeline: %s",
                        " → ".join(node_ids),
                    )
                    return {"_composed_manifest": manifest}
            except Exception:
                logger.warning(
                    "Tier 1 failed, trying LLM classification",
                    exc_info=True,
                )

        # Tier 2: LLM manifest classification
        if settings.GOOGLE_API_KEY:
            try:
                manifest_id = await self._llm_classify_fallback(state)
                if manifest_id:
                    logger.info("LLM classify selected: %s", manifest_id)
                    return {"resolved_manifest_id": manifest_id}
            except Exception:
                logger.warning(
                    "Tier 2 failed, falling back to keywords",
                    exc_info=True,
                )

        # Tier 3: Keyword matching
        resolved_id = self._keyword_fallback(state)
        logger.info("Keyword fallback resolved to: %s", resolved_id)
        return {"resolved_manifest_id": resolved_id}

    # ── Tier 1: Gemini Dynamic Composition ──

    def _enrich_system_prompt(self, state: AgentState) -> str:
        """Append company context, RAG hints, manifest reference, and
        few-shot examples to the base system prompt."""
        parts = [self._base_system_prompt]
        ctx = state.get("input_context") or {}

        # Company context
        company_name = ctx.get("company_name")
        sector = ctx.get("sector")
        brand_voice = ctx.get("brand_voice")
        if company_name or sector or brand_voice:
            context_lines = []
            if company_name:
                context_lines.append(f"Company: {company_name}")
            if sector:
                context_lines.append(f"Sector: {sector}")
            if brand_voice:
                context_lines.append(f"Brand voice: {brand_voice}")
            parts.append("\n\nCompany context:\n" + "\n".join(context_lines))

        # RAG hint
        if ctx.get("needs_rag"):
            parts.append(
                "\n\nIMPORTANT: The user has uploaded documents. Prefer "
                "default_agent over web_research when the prompt "
                "references their documents or knowledge base."
            )

        # Manifest reference
        available = state.get("available_manifests") or []
        if available:
            manifest_lines = "\n".join(
                f"- {m['pipeline_id']}: {m.get('description', m.get('name', ''))}"
                for m in available
            )
            parts.append(f"\n\nAvailable pipeline manifests:\n{manifest_lines}")

        # Few-shot examples
        parts.append(f"\n\n{_FEW_SHOT_EXAMPLES}")

        return "".join(parts)

    @staticmethod
    def _build_user_message(state: AgentState) -> str:
        """Build the user-facing message for Gemini, including recent
        chat history when available."""
        prompt = sanitize_ai_prompt(state.get("input_prompt", ""))
        ctx = state.get("input_context") or {}
        chat_history = ctx.get("chat_history")

        if chat_history and isinstance(chat_history, list):
            # Include last 3 messages for context
            recent = chat_history[-3:]
            history_lines = []
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_lines.append(f"  {role}: {content}")
            history_text = "\n".join(history_lines)
            return (
                f"Recent conversation:\n{history_text}\n\n" f"Current request: {prompt}"
            )

        return prompt

    async def _gemini_compose(self, state: AgentState) -> list[str] | None:
        """Use Gemini function-calling to select and order nodes.

        Retries up to GEMINI_COMPOSE_MAX_RETRIES times with exponential
        backoff on failure.
        """
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        system_prompt = self._enrich_system_prompt(state)
        user_message = self._build_user_message(state)

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_prompt,
            tools=[self._tool],
        )

        max_retries = settings.GEMINI_COMPOSE_MAX_RETRIES
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await model.generate_content_async(
                    user_message,
                    tool_config={"function_calling_config": {"mode": "ANY"}},
                )

                # Extract the function call
                for part in response.parts:
                    if fn := part.function_call:
                        if fn.name == "compose_pipeline":
                            raw_ids = list(fn.args.get("node_ids", []))
                            result = self._validate_node_ids(raw_ids)
                            if result:
                                logger.info(
                                    "Gemini composed pipeline (attempt %d): %s",
                                    attempt + 1,
                                    " → ".join(result),
                                )
                                return result

                logger.warning(
                    "Gemini did not return a compose_pipeline call " "(attempt %d)",
                    attempt + 1,
                )
                return None

            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = settings.GEMINI_COMPOSE_RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        "Gemini composition attempt %d failed, "
                        "retrying in %.1fs: %s",
                        attempt + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        # Exhausted retries — re-raise so compose() catches it
        raise last_exc  # type: ignore[misc]

    # ── Tier 2: LLM Manifest Classification ──

    async def _llm_classify_fallback(self, state: AgentState) -> str | None:
        """Use a lightweight Gemini call to select ONE pipeline_id
        from the 9 available manifests."""
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        ctx = state.get("input_context") or {}
        needs_rag = bool(ctx.get("needs_rag"))
        system_prompt = _build_classify_system_prompt(needs_rag)
        prompt = sanitize_ai_prompt(state.get("input_prompt", ""))

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_prompt,
            tools=[self._classify_tool],
        )

        response = await model.generate_content_async(
            prompt,
            tool_config={"function_calling_config": {"mode": "ANY"}},
        )

        valid_ids = {p["id"] for p in _PIPELINE_DESCRIPTIONS}

        for part in response.parts:
            if fn := part.function_call:
                if fn.name == "select_pipeline":
                    pipeline_id = fn.args.get("pipeline_id", "")
                    reason = fn.args.get("reason", "")
                    if pipeline_id in valid_ids:
                        logger.info(
                            "LLM classify selected '%s': %s",
                            pipeline_id,
                            reason,
                        )
                        return pipeline_id
                    logger.warning(
                        "LLM classify returned invalid pipeline_id: %s",
                        pipeline_id,
                    )
                    return None

        logger.warning("LLM classify did not return a select_pipeline call")
        return None

    # ── Tier 3: Keyword Fallback ──

    @staticmethod
    def _keyword_fallback(state: AgentState) -> str:
        """Fall back to improved keyword matching with stemming and
        RAG boosting (reuses shared keyword_match function)."""
        return keyword_match(state)

    # ── Shared helpers ──

    def _validate_node_ids(self, raw_ids: list[str]) -> list[str] | None:
        """Validate and sanitize node IDs from Gemini response."""
        valid_ids = set(self._catalog_map.keys()) | {"manager"}
        filtered = [nid for nid in raw_ids if nid in valid_ids]

        if not filtered:
            return None

        # Ensure manager is always last
        if "manager" in filtered and filtered[-1] != "manager":
            filtered.remove("manager")
            filtered.append("manager")
        elif "manager" not in filtered:
            filtered.append("manager")

        return filtered

    def _build_manifest(self, node_ids: list[str]) -> dict[str, Any]:
        """Build a complete manifest dict from an ordered list of node IDs."""
        nodes: list[dict[str, Any]] = []
        for nid in node_ids:
            if nid == "manager":
                nodes.append(
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    }
                )
                continue

            entry = self._catalog_map[nid]
            node_def: dict[str, Any] = {"id": nid, "type": entry["type"]}
            if entry["type"] == "internal":
                node_def["handler"] = entry["handler"]
            else:
                node_def["url"] = entry["url"]
            if entry.get("config"):
                node_def["config"] = entry["config"]
            nodes.append(node_def)

        # Auto-wire: sequential edges n1→n2→n3→...
        edges = [[node_ids[i], node_ids[i + 1]] for i in range(len(node_ids) - 1)]

        return {
            "nodes": nodes,
            "edges": edges,
            "global_config": {
                "model": "gemini-2.0-flash",
                "temperature": 0.7,
            },
        }
