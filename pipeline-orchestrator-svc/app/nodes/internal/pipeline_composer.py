"""
PipelineComposer — Dynamic, catalog-driven pipeline composition.

Replaces RouterNode for auto-detect mode. Uses Gemini function-calling
to select and order agent nodes from NODE_CATALOG, then builds a
manifest on the fly. Falls back to keyword matching when Gemini is
unavailable.

Adding a new agent requires only one dict entry in NODE_CATALOG.
"""

import logging
from typing import Any

from app.core.config import settings
from app.nodes.internal.router_node import KEYWORD_MAP
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
        "url": "http://discovery-agent-svc:8020/v1/search",
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
        "url": "http://content-agent-svc:8050/v1/execute",
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
        "url": "http://social-agent-svc:8060/v1/execute",
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
        "url": "http://intelligence-agent-svc:8030/v1/iso-calc",
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
        "url": "http://intelligence-agent-svc:8030/v1/analyze",
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
        "url": "http://rag-uploader-agent-svc:8070/v1/execute",
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


def _build_system_prompt(catalog: list[dict]) -> str:
    """Build the system prompt from the current catalog."""
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


class PipelineComposer:
    """Dynamic pipeline composer using Gemini function-calling + keyword fallback."""

    def __init__(self) -> None:
        self._catalog = NODE_CATALOG
        self._catalog_map = NODE_CATALOG_MAP
        self._tool = _build_compose_tool(self._catalog)
        self._system_prompt = _build_system_prompt(self._catalog)

    async def compose(self, state: AgentState) -> dict[str, Any]:
        """Compose a pipeline for the given state.

        Returns either:
            {"_composed_manifest": {...}} — dynamic composition succeeded
            {"resolved_manifest_id": "..."} — keyword fallback
        """
        prompt = sanitize_ai_prompt(state.get("input_prompt", ""))

        # PRIMARY: Try Gemini function-calling
        if settings.GOOGLE_API_KEY:
            try:
                node_ids = await self._gemini_compose(prompt)
                if node_ids:
                    manifest = self._build_manifest(node_ids)
                    logger.info(
                        "Gemini composed pipeline: %s",
                        " → ".join(node_ids),
                    )
                    return {"_composed_manifest": manifest}
            except Exception:
                logger.warning(
                    "Gemini composition failed, falling back to keywords",
                    exc_info=True,
                )

        # FALLBACK: Keyword matching → resolve to manifest_id
        resolved_id = self._keyword_fallback(state)
        logger.info("Keyword fallback resolved to: %s", resolved_id)
        return {"resolved_manifest_id": resolved_id}

    async def _gemini_compose(self, prompt: str) -> list[str] | None:
        """Use Gemini function-calling to select and order nodes."""
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=self._system_prompt,
            tools=[self._tool],
        )

        response = await model.generate_content_async(
            prompt,
            tool_config={"function_calling_config": {"mode": "ANY"}},
        )

        # Extract the function call
        for part in response.parts:
            if fn := part.function_call:
                if fn.name == "compose_pipeline":
                    raw_ids = list(fn.args.get("node_ids", []))
                    return self._validate_node_ids(raw_ids)

        logger.warning("Gemini did not return a compose_pipeline call")
        return None

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
            "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
        }

    @staticmethod
    def _keyword_fallback(state: AgentState) -> str:
        """Fall back to keyword matching (reuses RouterNode's KEYWORD_MAP)."""
        prompt = state.get("input_prompt", "").lower()
        available = state.get("available_manifests") or []
        available_ids = {m["pipeline_id"] for m in available} if available else set()

        resolved_id = "brand-analysis"
        best_score = 0

        for pipeline_id, keywords in KEYWORD_MAP.items():
            if available_ids and pipeline_id not in available_ids:
                continue
            score = sum(weight for kw, weight in keywords if kw in prompt)
            if score > best_score:
                best_score = score
                resolved_id = pipeline_id

        return resolved_id
