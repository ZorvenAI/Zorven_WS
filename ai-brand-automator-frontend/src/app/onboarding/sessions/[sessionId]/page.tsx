'use client';

/**
 * /onboarding/sessions/[sessionId] — redirects to unified OIA screen.
 *
 * Kept as a redirect so existing bookmarks and links continue to work.
 */

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

import { useAuth } from '@/hooks/useAuth';

export default function SessionPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const sessionId = params?.sessionId;

  useEffect(() => {
    if (sessionId) {
      router.replace(`/onboarding?session=${sessionId}&tab=overview`);
    } else {
      router.replace('/onboarding');
    }
  }, [sessionId, router]);

  return <p className="p-4 text-sm text-brand-silver">Redirecting…</p>;
}
