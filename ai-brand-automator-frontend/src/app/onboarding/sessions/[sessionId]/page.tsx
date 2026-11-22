'use client';

/**
 * /onboarding/sessions/[sessionId] — redirects to unified OIA screen.
 *
 * Kept as a redirect so existing bookmarks and links continue to work.
 */

import { useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';

import { useAuth } from '@/hooks/useAuth';

export default function SessionPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params?.sessionId;

  useEffect(() => {
    if (sessionId) {
      const dest = new URLSearchParams();
      dest.set('session', sessionId);
      dest.set('tab', 'overview');
      const recording = searchParams?.get('recording');
      const t = searchParams?.get('t');
      if (recording) dest.set('recording', recording);
      if (t) dest.set('t', t);
      router.replace(`/onboarding?${dest.toString()}`);
    } else {
      router.replace('/onboarding');
    }
  }, [sessionId, router, searchParams]);

  return <p className="p-4 text-sm text-brand-silver">Redirecting…</p>;
}
