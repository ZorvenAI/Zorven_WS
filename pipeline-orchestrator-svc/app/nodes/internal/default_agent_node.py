"""
DefaultAgentNode — RAG specialist that answers questions using tenant documents.

Queries the tenant's Vertex AI Search data store for relevant document chunks,
then synthesizes a grounded, source-cited answer using Gemini. Emits real-time
Kafka trace events for frontend thought display.

Supports chat attachments: when input_context contains an "attachments" list,
downloads files from GCS and sends them to Gemini as multimodal content for
direct analysis (e.g., "Summarize this document").
"""

import logging
import re
import tempfile
from typing import Any

import google.generativeai as genai

from app.core.config import settings
from app.nodes.base import BaseNode
from app.nodes.tools.vertex_search_tool import SearchChunk, VertexSearchTool
from app.state.schema import AgentState
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the Prevision AI Assistant. You have access to the user's "
    "uploaded documents and files. When answering questions, prioritize "
    "information from the provided search results and attached files over "
    "your own training data. Always cite your sources by referencing the "
    "file names. If the search results don't contain relevant information, "
    "be transparent and say so, then provide your best general knowledge "
    "answer. Maintain a professional, helpful tone.\n\n"
    "IMPORTANT: If the user's question includes tasks beyond document "
    "research (such as writing a blog, publishing, scheduling, or posting "
    "to social media), focus ONLY on providing the relevant document "
    "information and research findings. Do NOT comment on whether you can "
    "or cannot perform those other tasks — other specialized agents in the "
    "pipeline handle them. Never say things like 'I cannot schedule posts' "
    "or 'you will need to manually do X'. Just provide the research data."
)


class DefaultAgentNode(BaseNode):
    """RAG specialist node: Vertex AI Search + Gemini answer synthesis."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._search_tool = VertexSearchTool()

    async def __call__(self, state: AgentState) -> dict:
        job_id = state.get("job_id", "")
        input_prompt = sanitize_ai_prompt(state.get("input_prompt", ""))
        input_context: dict[str, Any] = state.get("input_context", {}) or {}
        tenant_context: dict[str, Any] = state.get("tenant_context", {}) or {}

        tenant_id = tenant_context.get("tenant_id", "")
        data_store_override = tenant_context.get("rag_data_store_id")
        chat_history: list[dict[str, str]] = input_context.get("chat_history", [])
        attachments: list[dict[str, Any]] = input_context.get("attachments", [])

        # Download chat attachments from GCS if present
        attachment_files: list[tuple[str, bytes]] = []
        if attachments:
            await self._emit_trace(
                job_id, "started", "Reading your attached documents..."
            )
            attachment_files = await self._download_attachments(attachments)

        # Emit pre-search trace
        await self._emit_trace(
            job_id,
            "started",
            "Interpreting your question in the context of our chat...",
        )

        # Extract the core search query (strip operational noise)
        search_query = self._extract_search_query(input_prompt)
        if search_query != input_prompt:
            logger.info(
                "Extracted search query: %s (from prompt: %s)",
                search_query[:80],
                input_prompt[:80],
            )

        # Search Vertex AI
        await self._emit_trace(
            job_id,
            "started",
            "Searching through your onboarded documents for answers...",
        )
        chunks = await self._search_tool.search(
            query=search_query,
            tenant_id=tenant_id,
            data_store_id=data_store_override,
        )

        # Emit post-search trace with source names
        if attachment_files:
            att_names = [name for name, _ in attachment_files[:3]]
            thought = f"Analyzing {len(attachment_files)} attached file(s): {', '.join(att_names)}..."
        elif chunks:
            source_names = [c.source_name for c in chunks[:3]]
            thought = (
                f"Extracting relevant information from "
                f"{', '.join(source_names)}..."
            )
        else:
            thought = (
                "No matching documents found. "
                "Preparing a general knowledge response..."
            )
        await self._emit_trace(job_id, "started", thought)

        # Synthesize answer with Gemini
        answer = await self._synthesize(
            input_prompt, chunks, chat_history, attachment_files
        )

        # Emit completion trace
        await self._emit_trace(
            job_id,
            "completed",
            "Drafting a summary based on retrieved findings...",
        )

        # Build result — when attachments are present, they are the
        # primary sources; otherwise fall back to Vertex AI Search chunks.
        if attachment_files:
            sources = [
                {"name": att.get("file_name", ""), "uri": ""}
                for att in attachments
            ]
        else:
            sources = [
                {"name": c.source_name, "uri": c.source_uri} for c in chunks
            ]

        # Include raw document chunks for downstream nodes (e.g., blog_author)
        # that need the original document text, not just the synthesized summary.
        raw_context = "\n\n".join(
            f"[{c.source_name}]\n{c.text}" for c in chunks if c.text
        )

        result: dict[str, Any] = {
            "summary": answer,
            "raw_context": raw_context,
            "sources": sources,
            "findings": [answer],
            "recommendations": [],
            "grounded": bool(chunks) or bool(attachment_files),
        }

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["default_agent"] = result

        return {"result_data": result, "node_outputs": node_outputs}

    async def _download_attachments(
        self, attachments: list[dict[str, Any]]
    ) -> list[tuple[str, bytes]]:
        """Download attachment files from GCS.

        Returns list of (filename, content_bytes) tuples.
        Failures are logged but non-fatal (returns partial results).
        """
        from app.services.gcs_reader import download_from_gcs

        results: list[tuple[str, bytes]] = []
        for att in attachments:
            bucket = att.get("gcs_bucket", "")
            path = att.get("gcs_path", "")
            if not bucket or not path:
                continue
            downloaded = await download_from_gcs(bucket, path)
            if downloaded:
                filename = att.get("file_name", downloaded[0])
                results.append((filename, downloaded[1]))
        return results

    async def _synthesize(
        self,
        query: str,
        chunks: list[SearchChunk],
        chat_history: list[dict[str, str]],
        attachment_files: list[tuple[str, bytes]] | None = None,
    ) -> str:
        """Synthesize an answer using Gemini, grounded in search chunks.

        When attachment_files are provided, uploads them to Gemini's File API
        for multimodal analysis (PDFs, images, documents).
        """
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_MODEL)

            prompt_parts = [SYSTEM_PROMPT, ""]

            # Add chat history context
            if chat_history:
                prompt_parts.append("## Previous conversation:")
                for msg in chat_history[-5:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    prompt_parts.append(f"**{role}**: {content}")
                prompt_parts.append("")

            # When the user has attached files, focus on those.
            # Do NOT include Vertex AI Search results — the user
            # explicitly attached a document and wants it analyzed.
            if attachment_files:
                att_names = [name for name, _ in attachment_files]
                prompt_parts.append(
                    "## Attached files:\n"
                    "The user has attached the following file(s) to this "
                    f"message: {', '.join(att_names)}.\n"
                    "Focus your entire response on analyzing the content "
                    "of the attached file(s). Do NOT use search results "
                    "from the knowledge base. Cite the attached file name(s) "
                    "as your source."
                )
            elif chunks:
                prompt_parts.append("## Retrieved documents:")
                for i, chunk in enumerate(chunks, 1):
                    prompt_parts.append(
                        f"[Source {i}: {chunk.source_name}]\n{chunk.text}\n"
                    )
                prompt_parts.append(
                    "Use the above documents to answer the user's question. "
                    "Cite sources using their file names."
                )
            else:
                prompt_parts.append(
                    "No documents were found in the user's knowledge base. "
                    "Provide your best general knowledge answer and be "
                    "transparent that this is not from their uploaded files."
                )

            prompt_parts.append(f"\n## User question:\n{query}")

            full_prompt = "\n".join(prompt_parts)

            # Build content parts for Gemini
            # If attachments exist, upload them and include as multimodal parts
            if attachment_files:
                content_parts = []
                uploaded_files = []
                for filename, file_bytes in attachment_files:
                    try:
                        uploaded = self._upload_to_gemini(filename, file_bytes)
                        if uploaded:
                            content_parts.append(uploaded)
                            uploaded_files.append(uploaded)
                    except Exception:
                        logger.warning(
                            "Failed to upload %s to Gemini File API",
                            filename,
                            exc_info=True,
                        )
                # Text prompt goes last
                content_parts.append(full_prompt)

                response = await model.generate_content_async(
                    content_parts,
                    generation_config=genai.types.GenerationConfig(
                        temperature=settings.GEMINI_TEMPERATURE,
                    ),
                )

                # Clean up uploaded files
                for uf in uploaded_files:
                    try:
                        genai.delete_file(uf.name)
                    except Exception:
                        pass
            else:
                response = await model.generate_content_async(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=settings.GEMINI_TEMPERATURE,
                    ),
                )

            answer = response.text or ""

            # Append source citations footer if grounded
            source_names = []
            if chunks:
                source_names.extend(
                    c.source_name for c in chunks if c.source_name
                )
            if attachment_files:
                source_names.extend(name for name, _ in attachment_files)
            if source_names:
                source_list = ", ".join(source_names)
                answer += f"\n\n**Sources:** {source_list}"

            return answer

        except Exception:
            logger.warning("Gemini synthesis failed", exc_info=True)
            # Graceful degradation: return raw search chunk text
            if chunks:
                parts = [
                    f"**{c.source_name}**: {c.text}" for c in chunks[:3]
                ]
                return (
                    "I found some relevant information in your documents "
                    "but couldn't generate a synthesized answer:\n\n"
                    + "\n\n".join(parts)
                )
            if attachment_files:
                return (
                    "I received your attached files but was unable to "
                    "process them at this time. Please try again."
                )
            return (
                "I couldn't find relevant information in your uploaded "
                "documents and was unable to generate a response. "
                "Please try rephrasing your question."
            )

    @staticmethod
    def _upload_to_gemini(
        filename: str, file_bytes: bytes
    ) -> Any:
        """Upload a file to the Gemini File API for multimodal processing."""
        with tempfile.NamedTemporaryFile(
            suffix=f"_{filename}", delete=True
        ) as tmp:
            tmp.write(file_bytes)
            tmp.flush()
            return genai.upload_file(tmp.name, display_name=filename)

    @staticmethod
    def _extract_search_query(prompt: str) -> str:
        """Extract the document name or search topic from a composite prompt.

        When the DefaultAgentNode runs in a multi-agent pipeline, the full
        user prompt includes operational instructions (write, post, schedule)
        that pollute the Vertex AI search query. This extracts just the
        document reference or core topic.
        """
        # 1. Look for explicit document identifiers (UPPER_CASE_SNAKE_CASE)
        # e.g., AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT
        doc_refs = re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z][A-Z0-9]*)+\b", prompt)
        if doc_refs:
            return max(doc_refs, key=len)

        # 2. Look for quoted document names
        quoted = re.findall(r'"([^"]{3,})"', prompt)
        if not quoted:
            quoted = re.findall(r"'([^']{3,})'", prompt)
        if quoted:
            return max(quoted, key=len)

        # 3. No explicit document name — return the full prompt
        # (works fine for standalone RAG queries like "tell me about X")
        return prompt

    @staticmethod
    async def _emit_trace(
        job_id: str, status: str, last_thought: str
    ) -> None:
        """Emit a Kafka trace event (non-fatal if unavailable)."""
        try:
            from app.main import trace_producer

            await trace_producer.send_trace(
                job_id=job_id,
                node_id="default_agent",
                status=status,
                output={"last_thought": last_thought},
            )
        except Exception:
            logger.debug("Trace emit failed (non-fatal)", exc_info=True)
