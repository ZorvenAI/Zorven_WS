'use client';

/**
 * /onboarding — the Onboarding Interface (E-01, FR-UI-01).
 *
 * This route used to be a redirect: editors to wizard step 1, viewers to
 * /chat. FR-UI-01 changes that — "the onboarding icon opens the Onboarding
 * Interface rather than wizard step 1, and the interface offers both the
 * meeting-driven path and a direct link into the unchanged manual wizard".
 *
 * The wizard itself is untouched. /onboarding/step-1 through step-5 still
 * render and still work with no session and no meeting, which is NFR-COMPAT
 * and is asserted in __tests__/OnboardingHome.test.tsx rather than left to
 * inspection.
 *
 * No role redirect either. A Viewer now lands here and sees a read-only
 * variant (AC-3); previously they were bounced to /chat and could not reach
 * onboarding at all.
 */

import { useAuth } from '@/hooks/useAuth';
import OnboardingHome from '@/components/onboarding/OnboardingHome';

export default function OnboardingPage() {
  useAuth();
  return <OnboardingHome />;
}
