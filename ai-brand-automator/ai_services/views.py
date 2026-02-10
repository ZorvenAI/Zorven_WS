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
from .services import ai_service
from onboarding.models import Company


class ChatSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for ChatSession model"""

    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]

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


class AIGenerationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AI generations (read-only)"""

    queryset = AIGeneration.objects.all()
    serializer_class = AIGenerationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant:
            return AIGeneration.objects.filter(tenant=tenant)
        return AIGeneration.objects.none()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_with_ai(request):
    """Chat with AI using brand context"""
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

    # Add user message to session
    session.add_message("user", message)

    # Get AI response
    ai_response = ai_service.chat_with_brand_context(message, context)

    # Add AI response to session
    session.add_message("assistant", ai_response)

    return Response(
        {
            "session_id": session.session_id,
            "response": ai_response,
            "session": ChatSessionSerializer(session).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
