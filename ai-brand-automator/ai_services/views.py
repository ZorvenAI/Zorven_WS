import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import uuid

from django.db.models import Count, Subquery, OuterRef
from .models import ChatSession, ChatMessage, SessionAttachment, AIGeneration
from .serializers import (
    ChatSessionSerializer,
    ChatInputSerializer,
    ChatMessageModelSerializer,
    SessionAttachmentSerializer,
    AIGenerationSerializer,
    BrandStrategyRequestSerializer,
    BrandIdentityRequestSerializer,
    MarketAnalysisRequestSerializer,
)
from .services import ai_service, GeminiAIService
from onboarding.models import Company
from tenants.permissions import (
    RoleBasedPermissionMixin,
    IsTenantViewer,
    IsTenantEditor,
)

logger = logging.getLogger(__name__)


class ChatSessionViewSet(RoleBasedPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for ChatSession model.

    Permissions:
        - list, retrieve: IsTenantViewer
        - create, update, destroy: IsTenantEditor
    """

    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantEditor],
        "update": [IsAuthenticated, IsTenantEditor],
        "partial_update": [IsAuthenticated, IsTenantEditor],
        "destroy": [IsAuthenticated, IsTenantEditor],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        if not tenant:
            return ChatSession.objects.none()
        last_msg_subquery = (
            ChatMessage.objects.filter(session=OuterRef("pk"))
            .order_by("-created_at")
            .values("content")[:1]
        )
        return (
            ChatSession.objects.filter(tenant=tenant)
            .annotate(
                _message_count=Count("chat_messages"),
                _last_message_preview=Subquery(last_msg_subquery),
            )
            .order_by("-last_activity")
        )

    def list(self, request, *args, **kwargs):
        """List sessions with per-tenant caching."""
        tenant = getattr(request, "tenant", None)
        cache_key = None
        if tenant:
            page = request.query_params.get("page", "")
            page_size = request.query_params.get("page_size", "")
            ordering = request.query_params.get("ordering", "")
            cache_key = (
                f"chat:sessions:{tenant.id}:"
                f"page={page}:page_size={page_size}:ordering={ordering}"
            )
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        response = super().list(request, *args, **kwargs)

        if cache_key and response.status_code == 200:
            try:
                cache.set(cache_key, response.data, timeout=60)
            except Exception:
                pass

        return response

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        if not tenant:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "No tenant context. Please log in again to obtain "
                "a valid tenant-scoped token."
            )
        serializer.save(tenant=tenant, session_id=str(uuid.uuid4()))
        _invalidate_session_list_cache(tenant)

    def perform_destroy(self, instance):
        tenant = instance.tenant
        super().perform_destroy(instance)
        _invalidate_session_list_cache(tenant)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        """List messages for a chat session with pagination."""
        session = self.get_object()
        queryset = ChatMessage.objects.filter(session=session).prefetch_related(
            "attachments"
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ChatMessageModelSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ChatMessageModelSerializer(queryset, many=True)
        return Response(serializer.data)


class AIGenerationViewSet(RoleBasedPermissionMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet for AI generations (read-only).

    Permissions:
        - list, retrieve: IsTenantViewer
    """

    queryset = AIGeneration.objects.all()
    serializer_class = AIGenerationSerializer
    permission_classes = [IsAuthenticated]
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
    }

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            return AIGeneration.objects.filter(tenant=tenant)
        return AIGeneration.objects.none()


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def chat_with_ai(request):
    """Chat with AI using brand context."""
    serializer = ChatInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    message = serializer.validated_data["message"]
    session_id = serializer.validated_data.get("session_id")

    tenant = getattr(request, "tenant", None)

    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get or create chat session
    is_new_session = False
    if session_id:
        session = get_object_or_404(ChatSession, session_id=session_id, tenant=tenant)
    else:
        session = ChatSession.objects.create(
            tenant=tenant,
            session_id=str(uuid.uuid4()),
            title=f"Chat {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            context={"company": {}},
        )
        is_new_session = True

    # Check if a pipeline job is still running for this session
    pipeline_lock_key = f"lock:chat:pipeline:{session.session_id}"
    pipeline_job_id = cache.get(pipeline_lock_key)
    if pipeline_job_id:
        return Response(
            {
                "error": "A pipeline analysis is still running for this session.",
                "pipeline_job_id": pipeline_job_id,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Acquire write lock to prevent concurrent writes to same session
    lock_key = f"chat:lock:{session.session_id}"
    if not cache.add(lock_key, "1", timeout=30):
        return Response(
            {"error": "Another message is being processed. Please wait."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        return _process_chat_message(
            request, session, message, tenant, is_new_session, serializer
        )
    finally:
        cache.delete(lock_key)


def _process_chat_message(
    request, session, message, tenant, is_new_session, serializer
):
    """Process a chat message (extracted for write-lock wrapper)."""
    # Get company context if available
    try:
        company = Company.objects.get(tenant=tenant)
        context = {
            "tenant": tenant,
            "company": {
                "name": company.name,
                "industry": company.industry,
                "target_audience": company.target_audience,
                "core_problem": company.core_problem,
                "brand_voice": company.brand_voice,
            },
        }
    except Company.DoesNotExist:
        context = {"tenant": tenant, "company": {}}

    # Classify intent: pipeline analysis vs. conversation
    intent_result = GeminiAIService.classify_intent(message)

    # Force RAG intent when attachments are provided — the user attached
    # a file and expects it to be analyzed, regardless of keyword score.
    attachment_ids = serializer.validated_data.get("attachment_ids", [])
    if attachment_ids and intent_result["intent"] != "pipeline":
        intent_result = {"intent": "rag", "confidence": 1.0}

    if intent_result["intent"] == "rag":
        # RAG / document query — dispatch to orchestrator general-chat pipeline
        from orchestration.models import AnalysisJob
        from orchestration.tasks import dispatch_job_task

        # Build chat history for context
        history_msgs = ChatMessage.objects.filter(session=session).order_by(
            "-created_at"
        )[:10]
        chat_history = [
            {"role": m.role, "content": m.content} for m in reversed(history_msgs)
        ]

        # Look up chat attachments if provided
        attachments_data = []
        if attachment_ids:
            attachments = SessionAttachment.objects.filter(
                id__in=attachment_ids,
                session=session,
            ).select_related("asset")
            for att in attachments:
                if att.asset and att.asset.gcs_path:
                    attachments_data.append(
                        {
                            "id": att.id,
                            "asset_id": att.asset.id,
                            "file_name": att.file_name,
                            "file_type": att.file_type,
                            "gcs_bucket": att.asset.gcs_bucket,
                            "gcs_path": att.asset.gcs_path,
                        }
                    )

        job_context = {
            "source": "chat",
            "session_id": session.session_id,
            "user_id": request.user.id,
            "user_email": request.user.email,
            "chat_history": chat_history,
            "attachments": attachments_data,
        }

        job = AnalysisJob.objects.create(
            tenant=tenant,
            input_prompt=message,
            input_context=job_context,
            created_by=request.user,
        )
        dispatch_job_task.delay(job.id)

        cache.set(
            f"lock:chat:pipeline:{session.session_id}",
            str(job.job_id),
            timeout=300,
        )

        ai_response = (
            "I'm searching through your uploaded documents to answer "
            "your question. You can track the progress below."
        )

        user_msg = ChatMessage.objects.create(
            session=session, role="user", content=message
        )

        # Link pending attachments to the user message
        if attachment_ids:
            SessionAttachment.objects.filter(
                id__in=attachment_ids, session=session
            ).update(message=user_msg)
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=ai_response,
            metadata={"job_id": str(job.job_id)},
        )
        session.last_activity = timezone.now()
        session.save(update_fields=["last_activity"])
        _maybe_auto_title(session, message, is_new_session)
        _invalidate_session_list_cache(tenant)

        return Response(
            {
                "session_id": session.session_id,
                "response": ai_response,
                "thinking": "",
                "pipeline_job": {
                    "job_id": str(job.job_id),
                    "status": job.status,
                },
                "user_message_id": user_msg.id,
                "session_pk": session.pk,
                "session": ChatSessionSerializer(session).data,
            }
        )

    if intent_result["intent"] == "pipeline":
        # Lazy imports to avoid circular dependency with orchestration app
        from orchestration.models import AnalysisJob
        from orchestration.tasks import dispatch_job_task

        target_brand = GeminiAIService.extract_target_brand(message)

        # Check if brand lookup returned an error
        if target_brand and "error" in target_brand:
            ai_response = target_brand["error"]
            user_msg = ChatMessage.objects.create(
                session=session, role="user", content=message
            )
            ChatMessage.objects.create(
                session=session, role="assistant", content=ai_response
            )
            session.last_activity = timezone.now()
            session.save(update_fields=["last_activity"])
            _maybe_auto_title(session, message, is_new_session)
            _invalidate_session_list_cache(tenant)
            return Response(
                {
                    "session_id": session.session_id,
                    "response": ai_response,
                    "thinking": "",
                    "pipeline_job": None,
                    "user_message_id": user_msg.id,
                    "session_pk": session.pk,
                    "session": ChatSessionSerializer(session).data,
                }
            )

        # Inject recent chat history for context-aware pipeline reasoning
        history_msgs = ChatMessage.objects.filter(session=session).order_by(
            "-created_at"
        )[:10]
        chat_history = [
            {"role": m.role, "content": m.content} for m in reversed(history_msgs)
        ]

        job_context = {
            "source": "chat",
            "session_id": session.session_id,
            "user_id": request.user.id,
            "user_email": request.user.email,
            "chat_history": chat_history,
        }
        if target_brand:
            job_context["company_name"] = target_brand.get("company_name", "")
            job_context["sector"] = target_brand.get("sector", "default")
            for key in (
                "base_revenue",
                "growth_rate",
                "brand_awareness",
                "profit_margin",
                "customer_loyalty",
                "market_share",
            ):
                if key in target_brand:
                    job_context[key] = target_brand[key]
        else:
            company_info = context.get("company", {})
            if company_info:
                job_context["company_name"] = company_info.get("name", "")
                job_context["sector"] = company_info.get("industry", "default")
                job_context["target_audience"] = company_info.get("target_audience", "")
                job_context["brand_voice"] = company_info.get("brand_voice", "")
                job_context["core_problem"] = company_info.get("core_problem", "")

        job = AnalysisJob.objects.create(
            tenant=tenant,
            input_prompt=message,
            input_context=job_context,
            created_by=request.user,
        )
        dispatch_job_task.delay(job.id)

        # Set pipeline lock (5 min TTL) to prevent concurrent chat messages
        # while the pipeline runs. Cleared when result_handler processes
        # a terminal status.
        cache.set(
            f"lock:chat:pipeline:{session.session_id}",
            str(job.job_id),
            timeout=300,
        )

        # Detect social intent for a friendlier response message
        _msg_lower = message.lower()
        _social_cues = (
            "linkedin",
            "twitter",
            "tweet",
            "facebook",
            "instagram",
            "social",
            "post to",
            "share on",
            "promote",
        )
        if any(cue in _msg_lower for cue in _social_cues):
            ai_response = (
                "I'm working on your request — researching the topic, "
                "authoring the content, and preparing social posts. "
                "You can track the progress below."
            )
        elif any(cue in _msg_lower for cue in ("blog", "write", "article", "author")):
            ai_response = (
                "I've started a blog authoring pipeline for your request. "
                "You can track the progress below."
            )
        else:
            ai_response = (
                "I've started a brand analysis pipeline for your request. "
                "You can track the progress below."
            )

        user_msg = ChatMessage.objects.create(
            session=session, role="user", content=message
        )
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=ai_response,
            metadata={"job_id": str(job.job_id)},
        )
        session.last_activity = timezone.now()
        session.save(update_fields=["last_activity"])
        _maybe_auto_title(session, message, is_new_session)
        _invalidate_session_list_cache(tenant)

        return Response(
            {
                "session_id": session.session_id,
                "response": ai_response,
                "thinking": "",
                "pipeline_job": {
                    "job_id": str(job.job_id),
                    "status": job.status,
                },
                "user_message_id": user_msg.id,
                "session_pk": session.pk,
                "session": ChatSessionSerializer(session).data,
            }
        )

    # Normal conversation flow — use ChatMessage model
    # Build history BEFORE persisting current message to avoid duplicating
    # the user turn (it's sent separately as the current message to Gemini)
    history = list(
        ChatMessage.objects.filter(session=session)
        .order_by("created_at")
        .values("role", "content")
    )

    user_msg = ChatMessage.objects.create(session=session, role="user", content=message)

    ai_result = ai_service.chat_with_brand_context(message, context, history)

    ChatMessage.objects.create(
        session=session,
        role="assistant",
        content=ai_result["content"],
        thinking=ai_result.get("thinking", ""),
    )
    session.last_activity = timezone.now()
    session.save(update_fields=["last_activity"])
    _maybe_auto_title(session, message, is_new_session)
    _invalidate_session_list_cache(tenant)

    return Response(
        {
            "session_id": session.session_id,
            "response": ai_result["content"],
            "thinking": ai_result.get("thinking", ""),
            "pipeline_job": None,
            "user_message_id": user_msg.id,
            "session_pk": session.pk,
            "session": ChatSessionSerializer(session).data,
        }
    )


def _invalidate_session_list_cache(tenant):
    """Clear the cached session list for a tenant.

    Deletes the default (un-paginated) cache key. Paginated variants
    expire naturally via the 60-second TTL.
    """
    if tenant:
        try:
            cache.delete(f"chat:sessions:{tenant.id}:page=:page_size=:ordering=")
        except Exception:
            pass


def _maybe_auto_title(session, message, is_new_session):
    """Dispatch auto-titling for new sessions."""
    if not is_new_session:
        return

    # Try Kafka first (if enabled)
    if getattr(settings, "TITLING_KAFKA_ENABLED", False):
        try:
            from kafka_service.consumer import KafkaProducerService

            producer = KafkaProducerService()
            producer.send(
                "chat-titling-topic",
                {
                    "session_id": session.session_id,
                    "session_pk": session.pk,
                    "tenant_id": (str(session.tenant_id) if session.tenant_id else ""),
                    "first_message": message[:2000],
                },
                key=str(session.tenant_id) if session.tenant_id else None,
            )
            producer.flush(timeout=2.0)
            return
        except Exception:
            logger.warning("Kafka titling publish failed, falling back to Celery")

    # Celery fallback
    try:
        from .tasks import auto_title_session

        auto_title_session.delay(session.id)
    except Exception:
        pass


@api_view(["PATCH"])
@permission_classes([])
def update_session_title_internal(request, session_id):
    """Internal endpoint for the titling worker to update session titles.

    Authenticates via X-Worker-Token header (service-to-service).
    """
    import re

    # Verify worker token
    token = request.META.get("HTTP_X_WORKER_TOKEN", "")
    expected_token = getattr(settings, "WORKER_TOKEN", "")
    if not expected_token or token != expected_token:
        logger.warning(
            "Invalid worker token for title update on session %s", session_id
        )
        return Response(
            {"error": "Invalid worker token"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        session = ChatSession.objects.get(session_id=session_id)
    except ChatSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verify tenant ID if provided (prevents cross-tenant title injection)
    claimed_tenant = request.META.get("HTTP_X_TENANT_ID", "")
    if claimed_tenant and str(session.tenant_id) != claimed_tenant:
        logger.warning(
            "Tenant mismatch for session %s: claimed=%s actual=%s",
            session_id,
            claimed_tenant,
            session.tenant_id,
        )
        return Response(
            {"error": "Tenant mismatch"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Skip if already titled (not a default timestamp title)
    if session.title and not session.title.startswith("Chat "):
        return Response({"status": "already_titled"})

    title = request.data.get("title", "")
    if not title:
        return Response(
            {"error": "Title is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Sanitize: strip HTML tags and control characters
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"[\x00-\x1f\x7f]", "", title)
    title = title.strip()

    if not title:
        return Response(
            {"error": "Title is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session.title = title[:255]
    session.save(update_fields=["title"])
    logger.info(
        "Internal title update for session %s: '%s'",
        session_id,
        session.title,
    )

    # Invalidate cached session list (use tenant_id to avoid extra DB query)
    if session.tenant_id:
        try:
            cache.delete(
                f"chat:sessions:{session.tenant_id}:page=:page_size=:ordering="
            )
        except Exception:
            pass

    return Response({"status": "updated"})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def generate_brand_strategy(request):
    """Generate brand strategy using AI"""
    serializer = BrandStrategyRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    company_id = serializer.validated_data["company_id"]
    company = get_object_or_404(Company, id=company_id, tenant=tenant)

    # Prepare company data for AI
    company_data = {
        "tenant": tenant,
        "name": company.name,
        "industry": company.industry,
        "target_audience": company.target_audience,
        "core_problem": company.core_problem,
        "brand_voice": company.brand_voice,
    }

    # Generate brand strategy
    result = ai_service.generate_brand_strategy(company_data)

    # Update company with generated content
    company.vision_statement = result.get("vision_statement", "")
    company.mission_statement = result.get("mission_statement", "")
    company.values = result.get("values", "")
    company.positioning_statement = result.get("positioning_statement", "")
    company.save()

    return Response(
        {
            "success": True,
            "data": result,
            "company": {
                "id": company.id,
                "vision_statement": company.vision_statement,
                "mission_statement": company.mission_statement,
                "values": company.values,
                "positioning_statement": company.positioning_statement,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def generate_brand_identity(request):
    """Generate brand identity using AI"""
    serializer = BrandIdentityRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    company_id = serializer.validated_data["company_id"]
    company = get_object_or_404(Company, id=company_id, tenant=tenant)

    # Prepare company data for AI
    company_data = {
        "tenant": tenant,
        "name": company.name,
        "industry": company.industry,
        "brand_voice": company.brand_voice,
        "target_audience": company.target_audience,
    }

    # Generate brand identity
    result = ai_service.generate_brand_identity(company_data)

    # Update company with generated content
    company.color_palette_desc = result.get("color_palette_desc", "")
    company.font_recommendations = result.get("font_recommendations", "")
    company.messaging_guide = result.get("messaging_guide", "")
    company.save()

    return Response(
        {
            "success": True,
            "data": result,
            "company": {
                "id": company.id,
                "color_palette_desc": company.color_palette_desc,
                "font_recommendations": company.font_recommendations,
                "messaging_guide": company.messaging_guide,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def analyze_market(request):
    """Perform market analysis using AI"""
    serializer = MarketAnalysisRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    company_id = serializer.validated_data["company_id"]
    company = get_object_or_404(Company, id=company_id, tenant=tenant)

    # Prepare company data for AI
    company_data = {
        "tenant": tenant,
        "name": company.name,
        "industry": company.industry,
        "target_audience": company.target_audience,
        "core_problem": company.core_problem,
    }

    # Generate market analysis
    result = ai_service.analyze_market(company_data)

    return Response({"success": True, "data": result})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantEditor])
def upload_chat_attachment(request):
    """Upload a file in chat context, creating a BrandAsset and SessionAttachment.

    Reuses the existing BrandAsset + GCS upload + pipeline flow from
    the onboarding app.

    Required form fields:
        - file: the uploaded file
        - session_id: chat session UUID
    Optional:
        - message_id: ChatMessage pk to attach to (omit for pre-upload)
        - file_type: one of image/video/document/other (auto-detected if omitted)
    """
    from onboarding.models import BrandAsset
    from brand_automator.validators import validate_file_upload, sanitize_filename
    from files.services import gcs_service

    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Validate required fields
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response(
            {"error": "No file provided."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session_id = request.data.get("session_id")
    message_id = request.data.get("message_id")
    if not session_id:
        return Response(
            {"error": "session_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session = get_object_or_404(ChatSession, session_id=session_id, tenant=tenant)
    message = None
    if message_id:
        message = get_object_or_404(ChatMessage, id=message_id, session=session)

    # File validation
    allowed_types = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ]
    validation = validate_file_upload(uploaded_file, allowed_types, max_size_mb=50)
    if not validation["valid"]:
        return Response(
            {"error": validation["error"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    safe_filename = sanitize_filename(uploaded_file.name)

    # Auto-detect file_type if not provided
    file_type = request.data.get("file_type", "")
    if not file_type:
        ct = uploaded_file.content_type or ""
        if ct.startswith("image/"):
            file_type = "image"
        elif ct.startswith("video/"):
            file_type = "video"
        elif ct == "application/pdf" or "document" in ct:
            file_type = "document"
        else:
            file_type = "other"

    # Get company for the tenant
    company = Company.objects.filter(tenant=tenant).first()
    if not company:
        return Response(
            {"error": "No company found for this workspace."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Upload to GCS
    unique_id = uuid.uuid4().hex[:8]
    landing_path = f"_landing/{tenant.id}/{unique_id}_{safe_filename}"
    raw_bucket = tenant.get_raw_bucket() if tenant else gcs_service.bucket_name
    gcs_uploaded = False

    try:
        target_bucket = gcs_service.get_bucket(raw_bucket)
        if target_bucket:
            gcs_service.upload_file(
                uploaded_file,
                landing_path,
                uploaded_file.content_type,
                bucket_name=raw_bucket,
            )
            gcs_uploaded = True
        else:
            logger.warning(
                "GCS not configured, chat attachment record created "
                "without file storage."
            )
    except Exception:
        logger.exception("GCS upload failed for chat attachment.")
        return Response(
            {"error": "Failed to upload file."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Create or reuse BrandAsset record.
    # Chat users may re-upload the same filename; the unique constraint
    # on (tenant, company, file_name) would block a second create, so
    # we update the existing asset's GCS path to the new upload location.
    asset, _created = BrandAsset.objects.update_or_create(
        tenant=tenant,
        company=company,
        file_name=safe_filename,
        defaults={
            "file_type": file_type,
            "file_size": uploaded_file.size,
            "gcs_path": landing_path,
            "gcs_bucket": raw_bucket,
            "processed": False,
            "pipeline_status": "pending" if gcs_uploaded else "failed",
            "pipeline_error": "" if gcs_uploaded else "GCS not configured",
        },
    )

    # Trigger data pipeline for RAG indexing.
    # The pipeline will move the file from _landing/ → raw/ and update
    # BrandAsset.gcs_path.  The Celery dispatch task refreshes attachment
    # paths (_refresh_attachment_paths) before sending to the orchestrator,
    # so the orchestrator will use whichever path is current.
    if gcs_uploaded:
        try:
            from onboarding.services import get_pipeline_service

            pipeline_service = get_pipeline_service()
            pipeline_service.publish_asset_event(asset)
        except Exception as e:
            logger.warning(f"Pipeline dispatch failed for chat attachment: {e}")

    # Create SessionAttachment
    attachment = SessionAttachment.objects.create(
        message=message,
        session=session,
        asset=asset,
        file_name=safe_filename,
        file_type=file_type,
        file_size=uploaded_file.size,
        pipeline_status="pending" if gcs_uploaded else "failed",
    )

    serializer = SessionAttachmentSerializer(attachment)
    return Response(serializer.data, status=status.HTTP_201_CREATED)
