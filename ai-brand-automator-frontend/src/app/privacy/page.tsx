'use client';

/**
 * /privacy — GDPR settings and decisions for owners and admins.
 *
 * Hosts the erasure review queue, the legal hold period, and the retention
 * window (RetentionSettings existed before this page but was not rendered
 * anywhere).
 */

import { useEffect, useSyncExternalStore } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import ErasureReviewQueue from '@/components/privacy/ErasureReviewQueue';
import LegalHoldSettings from '@/components/privacy/LegalHoldSettings';
import RetentionSettings from '@/components/onboarding/RetentionSettings';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';

function subscribeNever(): () => void {
  return () => {};
}

export default function PrivacyPage() {
  useAuth();
  const router = useRouter();
  const { role, isAdmin } = useTenantRole();
  // True in the browser, false while rendering on the server: the role comes
  // from client storage, so nothing role-dependent renders before hydration.
  const hasMounted = useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );

  // Once the role is known, send everyone else back: erasure decisions are
  // for the same people who can request an erasure.
  useEffect(() => {
    if (hasMounted && role !== undefined && !isAdmin) {
      router.replace('/dashboard');
    }
  }, [hasMounted, role, isAdmin, router]);

  if (!hasMounted || !isAdmin) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-brand-silver">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading…
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Privacy</h1>
        <p className="mt-1 text-sm text-brand-silver">
          Erasure requests and how long this workspace keeps onboarding data.
        </p>
      </div>
      <ErasureReviewQueue />
      <LegalHoldSettings />
      <RetentionSettings />
    </main>
  );
}
