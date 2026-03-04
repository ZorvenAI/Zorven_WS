'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { SubscriptionStatus } from '@/components/subscription/SubscriptionStatus';
import { PaymentHistoryTable } from '@/components/subscription/PaymentHistoryTable';
import {
  subscriptionApi,
  Subscription,
  PaymentHistory,
} from '@/lib/api';

// Support email - can be configured via environment variable
const SUPPORT_EMAIL =
  process.env.NEXT_PUBLIC_SUPPORT_EMAIL || 'support@aibrandautomator.com';

export default function BillingPage() {
  useAuth();
  const router = useRouter();
  const { canManageBilling } = useTenantRole();

  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [payments, setPayments] = useState<PaymentHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [subscriptionData, paymentsData] = await Promise.all([
          subscriptionApi.getStatus(),
          subscriptionApi.getPaymentHistory(),
        ]);
        setSubscription(subscriptionData);
        setPayments(paymentsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, []);

  const handleManageBilling = async () => {
    setIsProcessing(true);
    setError(null);

    try {
      const { portal_url } = await subscriptionApi.createPortalSession();
      window.location.href = portal_url;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to open billing portal'
      );
      setIsProcessing(false);
    }
  };

  const handleCancelSubscription = async () => {
    if (
      !confirm(
        'Are you sure you want to cancel your subscription? You will still have access until the end of your billing period.'
      )
    ) {
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      await subscriptionApi.cancelSubscription();
      const updatedSubscription = await subscriptionApi.getStatus();
      setSubscription(updatedSubscription);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to cancel subscription'
      );
    } finally {
      setIsProcessing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-brand-midnight">
        <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />
        <div className="relative z-10 mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="animate-pulse">
            <div className="h-8 w-48 rounded bg-white/10" />
            <div className="mt-8 h-48 rounded-lg bg-white/5 border border-white/10" />
            <div className="mt-8 h-64 rounded-lg bg-white/5 border border-white/10" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-midnight">
      {/* Subtle aura glow */}
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />
      
      <div className="relative z-10 mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="font-heading text-3xl font-heading font-bold text-white">
              Billing & Subscription
            </h1>
            <p className="mt-1 text-sm text-brand-silver/70 font-body">
              Manage your subscription and view payment history
            </p>
          </div>
          <button
            onClick={() => router.push('/dashboard')}
            className="btn-secondary text-sm"
          >
            ← Back to Dashboard
          </button>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-6 glass-card p-4 border-red-500/30">
            <div className="flex">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                  clipRule="evenodd"
                />
              </svg>
              <p className="ml-3 text-sm text-red-400">{error}</p>
            </div>
          </div>
        )}

        {/* Current Subscription */}
        <div className="mb-8">
          <h2 className="font-heading mb-4 text-lg font-heading font-semibold text-white">
            Current Subscription
          </h2>
          <SubscriptionStatus
            subscription={subscription}
            onManageBilling={canManageBilling ? handleManageBilling : undefined}
            onCancelSubscription={canManageBilling ? handleCancelSubscription : undefined}
            isLoading={isProcessing}
          />

          {!subscription && canManageBilling && (
            <div className="mt-4">
              <button
                onClick={() => router.push('/subscription')}
                className="btn-primary"
              >
                View Available Plans
              </button>
            </div>
          )}

          {!canManageBilling && (
            <div className="mt-4 p-3 bg-white/5 border border-white/10 rounded-lg">
              <p className="text-sm text-brand-silver/50">
                Only workspace owners can manage billing and subscriptions.
              </p>
            </div>
          )}
        </div>

        {/* Payment History */}
        <div>
          <h2 className="font-heading mb-4 text-lg font-heading font-semibold text-white">
            Payment History
          </h2>
          <PaymentHistoryTable payments={payments} />
        </div>

        {/* Billing FAQ */}
        <div className="mt-12 glass-card p-6">
          <h3 className="font-heading text-lg font-heading font-semibold text-white">
            Need Help with Billing?
          </h3>
          <p className="mt-2 text-sm text-brand-silver/70 font-body">
            If you have questions about your billing or subscription, please
            contact our support team at{' '}
            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="text-brand-electric hover:text-brand-electric/80 transition-colors"
            >
              {SUPPORT_EMAIL}
            </a>
          </p>
          {canManageBilling && (
            <div className="mt-4 flex gap-4">
              <button
                onClick={handleManageBilling}
                disabled={!subscription || isProcessing}
                className="btn-secondary disabled:cursor-not-allowed disabled:opacity-50"
              >
                Update Payment Method
              </button>
              <button
                onClick={() => router.push('/subscription')}
                className="btn-secondary"
              >
                Change Plan
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
