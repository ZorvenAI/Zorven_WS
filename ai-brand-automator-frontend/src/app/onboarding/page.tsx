'use client';

import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { useEffect } from 'react';

export default function OnboardingPage() {
  useAuth(); // Protect this route
  const router = useRouter();
  const { canEdit } = useTenantRole();
  
  useEffect(() => {
    if (canEdit) {
      router.push('/onboarding/step-1');
    } else {
      // Viewers cannot access onboarding
      router.push('/chat');
    }
  }, [router, canEdit]);
}