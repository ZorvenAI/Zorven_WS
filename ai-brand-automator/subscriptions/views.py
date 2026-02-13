"""
Views for subscription management.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
import logging

from .models import SubscriptionPlan, Subscription, PaymentHistory
from .serializers import (
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    PaymentHistorySerializer,
    CreateCheckoutSessionSerializer,
    CreatePortalSessionSerializer,
)
from .services import stripe_service
from tenants.permissions import IsTenantViewer, IsTenantOwner

logger = logging.getLogger(__name__)


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing subscription plans"""

    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]  # Plans are public


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantViewer])
def get_subscription_status(request):
    """Get current subscription status for the tenant."""
    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        subscription = Subscription.objects.get(tenant=tenant)
        serializer = SubscriptionSerializer(subscription)
        return Response(serializer.data)
    except Subscription.DoesNotExist:
        return Response(
            {
                "status": "none",
                "message": "No active subscription",
                "plans_url": "/api/v1/subscriptions/plans/",
            }
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantOwner])
def create_checkout_session(request):
    """Create a Stripe Checkout session for subscription."""
    serializer = CreateCheckoutSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        plan = SubscriptionPlan.objects.get(
            id=serializer.validated_data["plan_id"],
            is_active=True,
        )
    except SubscriptionPlan.DoesNotExist:
        return Response(
            {"error": "Plan not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        session = stripe_service.create_checkout_session(
            tenant=tenant,
            plan=plan,
            success_url=serializer.validated_data["success_url"],
            cancel_url=serializer.validated_data["cancel_url"],
            email=request.user.email,
        )

        if session:
            return Response(
                {
                    "checkout_url": session.url,
                    "session_id": session.id,
                }
            )
        else:
            return Response(
                {"error": "Stripe not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    except Exception as e:
        logger.error(f"Checkout session creation failed: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantOwner])
def create_portal_session(request):
    """Create a Stripe Customer Portal session."""
    serializer = CreatePortalSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not tenant.stripe_customer_id:
        return Response(
            {"error": "No billing account found. Please subscribe first."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = stripe_service.create_portal_session(
            tenant=tenant,
            return_url=serializer.validated_data["return_url"],
        )

        if session:
            return Response({"portal_url": session.url})
        else:
            return Response(
                {"error": "Stripe not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    except Exception as e:
        logger.error(f"Portal session creation failed: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantOwner])
def cancel_subscription(request):
    """Cancel the current subscription."""
    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        subscription = Subscription.objects.get(tenant=tenant)
    except Subscription.DoesNotExist:
        return Response(
            {"error": "No subscription found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    at_period_end = request.data.get("at_period_end", True)
    # Validate at_period_end is a boolean
    if not isinstance(at_period_end, bool):
        return Response(
            {"detail": "at_period_end must be a boolean"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        stripe_service.cancel_subscription(subscription, at_period_end=at_period_end)
        return Response(
            {
                "message": "Subscription will be canceled"
                + (" at period end" if at_period_end else " immediately"),
                "cancel_at_period_end": at_period_end,
            }
        )
    except Exception as e:
        logger.error(f"Subscription cancellation failed: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantViewer])
def get_payment_history(request):
    """Get payment history for the tenant."""
    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    payments = PaymentHistory.objects.filter(tenant=tenant)[:20]
    serializer = PaymentHistorySerializer(payments, many=True)
    return Response(serializer.data)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        result = stripe_service.handle_webhook_event(payload, sig_header)
        return Response(result)
    except ValueError as e:
        logger.error(f"Webhook error: {e}")
        return Response(
            {"detail": "Invalid Stripe webhook payload."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
        return Response(
            {"detail": "Error processing Stripe webhook."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantOwner])
def sync_subscription(request):
    """Sync subscription status from Stripe (for after checkout)."""
    tenant = getattr(request, "tenant", None)
    if not tenant:
        return Response(
            {"error": "No tenant context. Please log in again."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        subscription = stripe_service.sync_subscription_from_stripe(tenant)
        serializer = SubscriptionSerializer(subscription)
        return Response(
            {
                "message": "Subscription synced successfully",
                "subscription": serializer.data,
            }
        )
    except ValueError as e:
        return Response(
            {"detail": str(e)},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.exception(f"Error syncing subscription: {e}")
        return Response(
            {"detail": "Error syncing subscription from Stripe."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
