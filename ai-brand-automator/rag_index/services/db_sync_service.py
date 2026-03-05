"""
DB-to-RAG Sync Service.

Builds structured documents from Django models and syncs them
to Vertex AI RAG stores via the SyncOrchestrator.

Each model has a dedicated document builder that produces a
Vertex AI json_data compatible dict with:
- document_type: model-specific type string
- metadata: structured fields (name, dates, IDs)
- extracted_text: concatenated text content for search
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Models eligible for DB-to-RAG sync
SYNCABLE_MODELS = {
    "Company": "onboarding.Company",
    "AnalysisJob": "orchestration.AnalysisJob",
    "ChatMessage": "ai_services.ChatMessage",
    "AIGeneration": "ai_services.AIGeneration",
    "ContentCalendar": "automation.ContentCalendar",
}

# Document ID prefixes for upsert idempotency
_DOC_ID_PREFIXES = {
    "Company": "company",
    "AnalysisJob": "analysis",
    "ChatMessage": "chat-msg",
    "AIGeneration": "ai-gen",
    "ContentCalendar": "content-cal",
}

# Maximum text length for extracted_text (Vertex AI limit)
_MAX_TEXT_LENGTH = 50_000


class DbSyncService:
    """Builds structured documents from Django models and dispatches to RAG."""

    def build_document(self, model_name: str, instance) -> dict | None:
        """Build a RAG document from a model instance.

        Args:
            model_name: Short name of the model (e.g., "Company")
            instance: Django model instance

        Returns:
            Document dict for Vertex AI, or None to skip sync.
        """
        builder = getattr(self, f"_build_{model_name.lower()}_doc", None)
        if builder is None:
            logger.warning("No document builder for model: %s", model_name)
            return None
        return builder(instance)

    def should_sync(self, model_name: str, instance) -> bool:
        """Check if this instance should be synced to RAG.

        Applies per-model filters (e.g., only COMPLETED jobs).
        """
        if model_name == "AnalysisJob":
            return getattr(instance, "status", "") == "completed"
        if model_name == "ChatMessage":
            return getattr(instance, "role", "") == "assistant"
        if model_name == "ContentCalendar":
            return getattr(instance, "status", "") == "published"
        return True

    def get_document_id(self, model_name: str, instance) -> str:
        """Generate deterministic document ID for upsert idempotency."""
        prefix = _DOC_ID_PREFIXES.get(model_name, model_name.lower())
        pk = getattr(instance, "job_id", None) or instance.pk
        return f"{prefix}-{pk}"

    def get_tenant_id(self, instance) -> str | None:
        """Extract tenant_id from model instance."""
        tenant = getattr(instance, "tenant", None)
        if tenant:
            return str(tenant.id)
        # ChatMessage → session → tenant
        session = getattr(instance, "session", None)
        if session:
            tenant = getattr(session, "tenant", None)
            if tenant:
                return str(tenant.id)
        return None

    def get_model_class(self, model_name: str):
        """Import and return the Django model class for a given name."""
        from django.apps import apps

        app_label_model = SYNCABLE_MODELS.get(model_name)
        if not app_label_model:
            raise ValueError(f"Unknown syncable model: {model_name}")
        app_label, model = app_label_model.split(".")
        return apps.get_model(app_label, model)

    # ------------------------------------------------------------------
    # Document Builders
    # ------------------------------------------------------------------

    def _build_company_doc(self, company) -> dict[str, Any]:
        """Build RAG document from Company with all text fields."""
        text_parts = []

        # Core profile
        _append(text_parts, "Company", company.name)
        _append(text_parts, "Description", company.description)
        _append(text_parts, "Industry", company.industry)
        _append(text_parts, "Website", getattr(company, "website", ""))

        # Target audience
        _append(text_parts, "Target Audience", company.target_audience)
        _append(text_parts, "Core Problem", company.core_problem)
        _append(text_parts, "Demographics", company.demographics)
        _append(text_parts, "Psychographics", company.psychographics)
        _append(text_parts, "Pain Points", company.pain_points)
        _append(text_parts, "Desired Outcomes", company.desired_outcomes)

        # Brand voice
        _append(text_parts, "Brand Voice", company.brand_voice)

        # AI-generated strategy
        _append(text_parts, "Vision Statement", company.vision_statement)
        _append(text_parts, "Mission Statement", company.mission_statement)
        _append(text_parts, "Values", company.values)
        _append(text_parts, "Positioning Statement", company.positioning_statement)

        # Messaging
        _append(text_parts, "Tagline", company.tagline)
        _append(text_parts, "Value Proposition", company.value_proposition)
        _append(text_parts, "Elevator Pitch", company.elevator_pitch)

        # Brand identity
        _append(text_parts, "Color Palette", company.color_palette_desc)
        _append(text_parts, "Font Recommendations", company.font_recommendations)
        _append(text_parts, "Messaging Guide", company.messaging_guide)

        # Asset summary
        try:
            asset_count = company.assets.count()
            if asset_count > 0:
                text_parts.append(f"Brand Assets: {asset_count} files uploaded")
        except Exception:
            pass

        return {
            "document_type": "company_profile",
            "metadata": {
                "name": company.name or "",
                "industry": company.industry or "",
                "brand_voice": company.brand_voice or "",
                "company_id": str(company.id),
                "created_at": _iso(company, "created_at"),
                "updated_at": _iso(company, "updated_at"),
            },
            "extracted_text": _truncate("\n\n".join(text_parts)),
        }

    def _build_analysisjob_doc(self, job) -> dict[str, Any]:
        """Build RAG document from a completed AnalysisJob."""
        text_parts = [f"Analysis Request: {job.input_prompt}"]

        # Summarise result_data (may be large JSON)
        if job.result_data:
            summary = _summarise_json(job.result_data, max_chars=10_000)
            text_parts.append(f"Results:\n{summary}")

        if job.error_message:
            text_parts.append(f"Error: {job.error_message}")

        return {
            "document_type": "analysis_job",
            "metadata": {
                "job_id": str(job.job_id),
                "status": job.status,
                "created_at": _iso(job, "created_at"),
                "completed_at": _iso(job, "completed_at"),
                "duration_seconds": job.duration_seconds,
            },
            "extracted_text": _truncate("\n\n".join(text_parts)),
        }

    def _build_chatmessage_doc(self, msg) -> dict[str, Any]:
        """Build RAG document from an assistant ChatMessage."""
        text_parts = [msg.content]

        # Include session context if available
        session = getattr(msg, "session", None)
        if session:
            title = getattr(session, "title", "")
            if title:
                text_parts.insert(0, f"Chat: {title}")

        return {
            "document_type": "chat_message",
            "metadata": {
                "role": msg.role,
                "session_id": str(msg.session_id) if msg.session_id else "",
                "created_at": _iso(msg, "created_at"),
            },
            "extracted_text": _truncate("\n\n".join(text_parts)),
        }

    def _build_aigeneration_doc(self, gen) -> dict[str, Any]:
        """Build RAG document from an AIGeneration."""
        text_parts = [
            f"Content Type: {gen.content_type}",
            f"Prompt: {gen.prompt}",
        ]

        # Truncate response to 10K chars
        response = (gen.response or "")[:10_000]
        if response:
            text_parts.append(f"Response:\n{response}")

        return {
            "document_type": "ai_generation",
            "metadata": {
                "content_type": gen.content_type,
                "model_used": gen.model_used or "",
                "tokens_used": gen.tokens_used or 0,
                "created_at": _iso(gen, "created_at"),
            },
            "extracted_text": _truncate("\n\n".join(text_parts)),
        }

    def _build_contentcalendar_doc(self, post) -> dict[str, Any]:
        """Build RAG document from a published ContentCalendar entry."""
        text_parts = [f"Title: {post.title}"]

        if post.content:
            text_parts.append(post.content)

        platforms = post.platforms or []
        if platforms:
            text_parts.append(f"Platforms: {', '.join(platforms)}")

        return {
            "document_type": "content_calendar",
            "metadata": {
                "title": post.title or "",
                "platforms": platforms,
                "status": post.status,
                "scheduled_date": _iso(post, "scheduled_date"),
                "published_at": _iso(post, "published_at"),
                "created_at": _iso(post, "created_at"),
            },
            "extracted_text": _truncate("\n\n".join(text_parts)),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _append(parts: list[str], label: str, value: str | None) -> None:
    """Append a labelled value to text parts if non-empty."""
    if value:
        parts.append(f"{label}: {value}")


def _iso(obj, attr: str) -> str | None:
    """Safely extract an ISO timestamp string from a model attribute."""
    val = getattr(obj, attr, None)
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _truncate(text: str) -> str:
    """Truncate text to Vertex AI limit."""
    if len(text) > _MAX_TEXT_LENGTH:
        return text[:_MAX_TEXT_LENGTH] + "\n... (truncated)"
    return text


def _summarise_json(data: Any, max_chars: int = 10_000) -> str:
    """Convert JSON data to a readable summary string."""
    if isinstance(data, str):
        return data[:max_chars]
    try:
        text = json.dumps(data, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(data)
    return text[:max_chars]
