'use client';

import { useParams } from 'next/navigation';

import { useAuth } from '@/hooks/useAuth';
import KeyFindingsReview from '@/components/onboarding/KeyFindingsReview';

export default function ReviewPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;

  if (!sessionId) {
    return (
      <p className="text-sm text-brand-silver">No session selected.</p>
    );
  }

  return <KeyFindingsReview sessionId={sessionId} />;
}
