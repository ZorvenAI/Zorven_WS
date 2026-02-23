import logging

from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import uuid

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
        if tenant:
            return ChatSession.objects.filter(tenant=tenant)
        return ChatSession.objects.none()

    def list(self, request, *args, **kwargs):
        """List sessions with per-tenant caching."""
        tenant = getattr(request, "tenant", None)
        if tenant:
            cache_key = f"chat:sessions:{tenant.id}"
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        response = super().list(request, *args, **kwargs)

        if tenant and response.status_code == 200:
            try:
                cache.set(
                    f"chat:sessions:{tenant.id}",
                    response.data,
                    timeout=60,  # 1 minute TTL
                )
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
        """List all messages for a chat session."""
        session = self.get_object()
        messages = ChatMessage.objects.filter(session=session)
        serializer = ChatMessageModelSerializer(messages, many=True)
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

    # Acquire write lock to prevent concurrent writes to same session
    lock_key = f"chat:lock:{session.session_id}"
    if not cache.add(lock_key, "1", timeout=30):
        return Response(
            {"error": "Another message is being processed. Please wait."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        return _process_chat_message(request, session, message, tenant, is_new_session)
    finally:
        cache.delete(lock_key)


def _process_chat_message(request, session, message, tenant, is_new_session):
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

    if intent_result["intent"] == "pipeline":
        # Lazy imports to avoid circular dependency with orchestration app
        from orchestration.models import AnalysisJob
        from orchestration.tasks import dispatch_job_task

        target_brand = GeminiAIService.extract_target_brand(message)

        # Check if brand lookup returned an error
        if target_brand and "error" in target_brand:
            ai_response = target_brand["error"]
            ChatMessage.objects.create(session=session, role="user", content=message)
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
                    "session": ChatSessionSerializer(session).data,
                }
            )

        job_context = {
            "source": "chat",
            "session_id": session.session_id,
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

        ai_response = (
            "I've started a brand analysis pipeline for your request. "
            "You can track the progress below."
        )

        ChatMessage.objects.create(session=session, role="user", content=message)
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
                "session": ChatSessionSerializer(session).data,
            }
        )

    # Normal conversation flow — use ChatMessage model
    ChatMessage.objects.create(session=session, role="user", content=message)

    # Build history from ChatMessage records for Gemini context
    history = list(
        ChatMessage.objects.filter(session=session)
        .order_by("created_at")
        .values("role", "content")
    )

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
            "session": ChatSessionSerializer(session).data,
        }
    )


def _invalidate_session_list_cache(tenant):
    """Clear the cached session list for a tenant."""
    if tenant:
        try:
            cache.delete(f"chat:sessions:{tenant.id}")
        except Exception:
            pass


def _maybe_auto_title(session, message, is_new_session):
    """Dispatch auto-titling for new sessions."""
    if not is_new_session:
        return
    try:
        from .tasks import auto_title_session

        auto_title_session.delay(session.id)
    except Exception:
        pass


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
        - message_id: ChatMessage pk to attach to
    Optional:
        - file_type: one of image/video/document/other (auto-detected if omitted)
    """
    from onboarding.models import BrandAsset
    from onboarding.views import validate_file_upload, sanitize_filename
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
    if not session_id or not message_id:
        return Response(
            {"error": "session_id and message_id are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session = get_object_or_404(ChatSession, session_id=session_id, tenant=tenant)
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
    except Exception as e:
        logger.error(f"GCS upload failed for chat attachment: {e}")
        return Response(
            {"error": f"Failed to upload file: {e}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Create BrandAsset record (reuse existing pipeline integration)
    asset = BrandAsset.objects.create(
        tenant=tenant,
        company=company,
        file_name=safe_filename,
        file_type=file_type,
        file_size=uploaded_file.size,
        gcs_path=landing_path,
        gcs_bucket=raw_bucket,
        processed=False,
        pipeline_status="pending" if gcs_uploaded else "failed",
        pipeline_error="" if gcs_uploaded else "GCS not configured",
    )

    # Trigger data pipeline
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
        asset=asset,
        file_name=safe_filename,
        file_type=file_type,
        file_size=uploaded_file.size,
        pipeline_status="pending" if gcs_uploaded else "failed",
    )

    serializer = SessionAttachmentSerializer(attachment)
    return Response(serializer.data, status=status.HTTP_201_CREATED)
