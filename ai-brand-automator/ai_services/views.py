from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import uuid

from .models import ChatSession, AIGeneration
from .serializers import (
    ChatSessionSerializer,
    ChatMessageSerializer,
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

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        if not tenant:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "No tenant context. Please log in again to obtain "
                "a valid tenant-scoped token."
            )
        serializer.save(tenant=tenant, session_id=str(uuid.uuid4()))


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
    serializer = ChatMessageSerializer(data=request.data)
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
    if session_id:
        session = get_object_or_404(ChatSession, session_id=session_id, tenant=tenant)
    else:
        session = ChatSession.objects.create(
            tenant=tenant,
            session_id=str(uuid.uuid4()),
            title=f"Chat {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            context={"company": {}},
        )

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

        # Build brand-specific context for the pipeline.
        # First, try to extract the target brand from the message
        # (e.g., "calculate brand equity for Nike" → Nike).
        # If not found, fall back to the tenant's own company data.
        target_brand = GeminiAIService.extract_target_brand(message)

        # Check if brand lookup returned an error
        if target_brand and "error" in target_brand:
            ai_response = target_brand["error"]
            session.add_message("user", message)
            session.add_message("assistant", ai_response)
            return Response(
                {
                    "session_id": session.session_id,
                    "response": ai_response,
                    "pipeline_job": None,
                    "session": ChatSessionSerializer(session).data,
                }
            )

        job_context = {
            "source": "chat",
            "session_id": session.session_id,
        }
        if target_brand:
            # Use the looked-up brand data
            job_context["company_name"] = target_brand.get("company_name", "")
            job_context["sector"] = target_brand.get("sector", "default")
            if "base_revenue" in target_brand:
                job_context["base_revenue"] = target_brand["base_revenue"]
            if "growth_rate" in target_brand:
                job_context["growth_rate"] = target_brand["growth_rate"]
            if "brand_awareness" in target_brand:
                job_context["brand_awareness"] = target_brand["brand_awareness"]
            if "profit_margin" in target_brand:
                job_context["profit_margin"] = target_brand["profit_margin"]
            if "customer_loyalty" in target_brand:
                job_context["customer_loyalty"] = target_brand["customer_loyalty"]
            if "market_share" in target_brand:
                job_context["market_share"] = target_brand["market_share"]
        else:
            # Fall back to the tenant's own company data
            company_info = context.get("company", {})
            if company_info:
                job_context["company_name"] = company_info.get("name", "")
                job_context["sector"] = company_info.get("industry", "default")
                job_context["target_audience"] = company_info.get("target_audience", "")
                job_context["brand_voice"] = company_info.get("brand_voice", "")
                job_context["core_problem"] = company_info.get("core_problem", "")

        # Create analysis job linked to this chat session
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

        session.add_message("user", message)
        session.add_message(
            "assistant", ai_response, metadata={"job_id": str(job.job_id)}
        )

        return Response(
            {
                "session_id": session.session_id,
                "response": ai_response,
                "pipeline_job": {
                    "job_id": str(job.job_id),
                    "status": job.status,
                },
                "session": ChatSessionSerializer(session).data,
            }
        )

    # Normal conversation flow
    session.add_message("user", message)
    ai_response = ai_service.chat_with_brand_context(message, context)
    session.add_message("assistant", ai_response)

    return Response(
        {
            "session_id": session.session_id,
            "response": ai_response,
            "pipeline_job": None,
            "session": ChatSessionSerializer(session).data,
        }
    )


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
