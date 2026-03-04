'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { PlanCard } from '@/components/subscription/PlanCard';
import { SubscriptionStatus } from '@/components/subscription/SubscriptionStatus';
import {
  subscriptionApi,
  SubscriptionPlan,
  Subscription,
} from '@/lib/api';

function SubscriptionContent() {
  useAuth();
  const { canManageBilling } = useTenantRole();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        // Check if returning from successful checkout
        const success = searchParams.get('success');
        if (success === 'true') {
          setSuccessMessage('Payment successful! Syncing your subscription...');
          // Sync subscription from Stripe
          try {
            await subscriptionApi.syncSubscription();
            setSuccessMessage('Subscription activated successfully!');
          } catch {
            // Subscription might already be synced via webhook
          }
          // Clear the query params without triggering a re-render loop
          window.history.replaceState({}, '', '/subscription');
        }

        // Fetch fresh data after sync
        const [plansData, subscriptionData] = await Promise.all([
          subscriptionApi.getPlans(),
          subscriptionApi.getStatus(),
        ]);
        setPlans(plansData);
        setSubscription(subscriptionData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [searchParams]);

  const handleSelectPlan = async (plan: SubscriptionPlan) => {
    setIsProcessing(true);
    setError(null);

    try {
      const { checkout_url } = await subscriptionApi.createCheckoutSession(
        plan.id
      );
      // Redirect to Stripe checkout
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setIsProcessing(false);
    }
  };

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
      // Refresh subscription status
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
        <div className="relative z-10 mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="animate-pulse">
            <div className="mx-auto h-8 w-64 rounded bg-white/10" />
            <div className="mx-auto mt-4 h-4 w-96 rounded bg-white/10" />
            <div className="mt-16 grid gap-8 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-96 rounded-2xl bg-white/5 border border-white/10" />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-midnight">
      {/* Subtle aura glow */}
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />
      
      <div className="relative z-10 mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center">
          <h1 className="font-heading text-4xl font-heading font-bold tracking-tight text-white sm:text-5xl">
            Choose Your Plan
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-brand-silver/80 font-body">
            Select the perfect plan for your brand building needs. All plans
            include our core AI-powered features.
          </p>
        </div>

        {/* Success message */}
        {successMessage && (
          <div className="mx-auto mt-8 max-w-md">
            <div className="glass-card p-4 border-brand-mint/30">
              <div className="flex">
                <svg
                  className="h-5 w-5 text-brand-mint"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="ml-3 text-sm text-brand-mint">{successMessage}</p>
              </div>
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="mx-auto mt-8 max-w-md">
            <div className="glass-card p-4 border-red-500/30">
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
          </div>
        )}

        {/* Current subscription status */}
        {subscription && (
          <div className="mx-auto mt-12 max-w-md">
            <SubscriptionStatus
              subscription={subscription}
              onManageBilling={canManageBilling ? handleManageBilling : undefined}
              onCancelSubscription={canManageBilling ? handleCancelSubscription : undefined}
              isLoading={isProcessing}
            />
          </div>
        )}

        {/* Plans grid */}
        <div className="mx-auto mt-16 grid max-w-5xl gap-8 lg:grid-cols-3">
          {plans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              isCurrentPlan={subscription?.plan?.id === plan.id}
              onSelect={canManageBilling ? handleSelectPlan : undefined}
              isLoading={isProcessing}
            />
          ))}
        </div>

        {!canManageBilling && (
          <div className="mx-auto mt-8 max-w-md">
            <div className="glass-card p-4 border-white/10">
              <p className="text-sm text-brand-silver/50 text-center">
                Only workspace owners can manage billing and change plans.
              </p>
            </div>
          </div>
        )}

        {/* Back to dashboard link */}
        <div className="mt-12 text-center">
          <button
            onClick={() => router.push('/dashboard')}
            className="text-sm font-medium text-brand-electric hover:text-brand-electric/80 transition-colors"
          >
            ← Back to Dashboard
          </button>
        </div>

        {/* FAQ or additional info */}
        <div className="mx-auto mt-16 max-w-3xl glass-card p-8">
          <h2 className="font-heading text-center text-2xl font-heading font-bold text-white">
            Frequently Asked Questions
          </h2>
          <dl className="mt-8 space-y-6">
            <div>
              <dt className="text-lg font-heading font-semibold text-white">
                Can I change my plan later?
              </dt>
              <dd className="mt-2 text-brand-silver/70 font-body">
                Yes! You can upgrade or downgrade your plan at any time. Changes
                will be prorated and applied to your next billing cycle.
              </dd>
            </div>
            <div>
              <dt className="text-lg font-heading font-semibold text-white">
                What payment methods do you accept?
              </dt>
              <dd className="mt-2 text-brand-silver/70 font-body">
                We accept all major credit cards (Visa, MasterCard, American
                Express) through our secure Stripe payment processor.
              </dd>
            </div>
            <div>
              <dt className="text-lg font-heading font-semibold text-white">
                Is there a free trial?
              </dt>
              <dd className="mt-2 text-brand-silver/70 font-body">
                We don&apos;t currently offer a free trial. You can start with
                any monthly plan and cancel anytime before your next billing
                period.
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}

function SubscriptionLoadingFallback() {
  return (
    <div className="min-h-screen bg-brand-midnight flex items-center justify-center">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />
      <div className="relative z-10 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-electric mx-auto"></div>
        <p className="mt-4 text-brand-silver/70 font-body">Loading subscription...</p>
      </div>
    </div>
  );
}

export default function SubscriptionPage() {
  return (
    <Suspense fallback={<SubscriptionLoadingFallback />}>
      <SubscriptionContent />
    </Suspense>
  );
}
