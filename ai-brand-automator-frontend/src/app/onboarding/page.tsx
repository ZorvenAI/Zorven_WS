'use client';

/**
 * /onboarding — unified OIA interface.
 *
 * All OIA functionality (sessions, meeting view, review, calendar, chat)
 * in one master-detail screen. The 5-step wizard forms (step-1 through
 * step-5) are untouched and linked from the header.
 *
 * Query params drive state: ?session=xxx&tab=overview|meeting|review|calendar
 * so deep links and browser back/forward work.
 */

import { Suspense } from 'react';

import { useAuth } from '@/hooks/useAuth';
import OnboardingUnified from '@/components/onboarding/OnboardingUnified';

export default function OnboardingPage() {
  useAuth();
  return (
    <Suspense fallback={<div className="p-4 text-sm text-brand-silver">Loading…</div>}>
      <OnboardingUnified />
    </Suspense>
  );
}
