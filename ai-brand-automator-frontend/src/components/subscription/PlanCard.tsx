'use client';

import { SubscriptionPlan } from '@/lib/api';

interface PlanCardProps {
  plan: SubscriptionPlan;
  isCurrentPlan?: boolean;
  onSelect?: (plan: SubscriptionPlan) => void;
  isLoading?: boolean;
}

export function PlanCard({ plan, isCurrentPlan, onSelect, isLoading }: PlanCardProps) {
  const isPro = plan.name === 'pro';
  const isEnterprise = plan.name === 'enterprise';

  // Build feature list based on plan features
  const featureList = [
    plan.description,
    plan.max_brands === -1 ? 'Unlimited brands' : `${plan.max_brands} brand${plan.max_brands > 1 ? 's' : ''}`,
    plan.ai_generations_per_month === -1 ? 'Unlimited AI generations' : `${plan.ai_generations_per_month} AI generations/month`,
    plan.max_team_members === -1 ? 'Unlimited team members' : `${plan.max_team_members} team member${plan.max_team_members > 1 ? 's' : ''}`,
    plan.automation_enabled ? 'Social media automation' : null,
    plan.priority_support ? 'Priority support' : 'Email support',
  ].filter(Boolean) as string[];

  return (
    <div
      className={`relative glass-card p-8 transition-all hover:scale-[1.02] ${
        isPro
          ? 'border-brand-electric ring-2 ring-brand-electric/50'
          : ''
      } ${isCurrentPlan ? 'ring-2 ring-brand-mint/50' : ''}`}
    >
      {isPro && (
        <div className="absolute -top-4 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center rounded-full bg-brand-electric px-4 py-1 text-sm font-semibold text-brand-midnight">
            Most Popular
          </span>
        </div>
      )}

      {isCurrentPlan && (
        <div className="absolute -top-4 right-4">
          <span className="inline-flex items-center rounded-full bg-brand-mint px-4 py-1 text-sm font-semibold text-brand-midnight">
            Current Plan
          </span>
        </div>
      )}

      <div className="text-center">
        <h3 className="text-xl font-heading font-semibold text-white">{plan.display_name}</h3>
        <div className="mt-4 flex items-baseline justify-center gap-x-2">
          <span className="text-5xl font-heading font-bold tracking-tight text-white">
            ${parseFloat(plan.price).toFixed(0)}
          </span>
          <span className="text-sm font-semibold leading-6 tracking-wide text-brand-silver/70">
            /month
          </span>
        </div>
      </div>

      <ul className="mt-8 space-y-3">
        {featureList.map((feature, index) => (
          <li key={index} className="flex items-start gap-3">
            <svg
              className="h-6 w-6 flex-shrink-0 text-brand-electric"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4.5 12.75l6 6 9-13.5"
              />
            </svg>
            <span className="text-sm text-brand-silver/80 font-body">{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-8 space-y-2">
        <div className="flex justify-between text-sm text-brand-silver/70">
          <span>Brands:</span>
          <span className="font-medium text-white">
            {plan.max_brands === -1 ? 'Unlimited' : plan.max_brands}
          </span>
        </div>
        <div className="flex justify-between text-sm text-brand-silver/70">
          <span>AI Generations:</span>
          <span className="font-medium text-white">
            {plan.ai_generations_per_month === -1
              ? 'Unlimited'
              : `${plan.ai_generations_per_month}/month`}
          </span>
        </div>
        <div className="flex justify-between text-sm text-brand-silver/70">
          <span>Team Members:</span>
          <span className="font-medium text-white">
            {plan.max_team_members === -1 ? 'Unlimited' : plan.max_team_members}
          </span>
        </div>
      </div>

      <button
        onClick={() => onSelect?.(plan)}
        disabled={isLoading || isCurrentPlan || !onSelect}
        className={`mt-8 w-full rounded-lg px-4 py-3 text-center text-sm font-semibold transition-all ${
          isCurrentPlan
            ? 'cursor-not-allowed bg-white/10 text-brand-silver/50'
            : isPro
            ? 'btn-primary'
            : isEnterprise
            ? 'bg-brand-ghost text-white hover:bg-brand-ghost/80'
            : 'btn-secondary'
        } ${isLoading ? 'cursor-wait opacity-75' : ''}`}
      >
        {isLoading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Processing...
          </span>
        ) : isCurrentPlan ? (
          'Current Plan'
        ) : (
          `Get ${plan.display_name}`
        )}
      </button>
    </div>
  );
}
