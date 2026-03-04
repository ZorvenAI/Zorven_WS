'use client';

import Link from 'next/link';
import { StepWizard } from '@/components/onboarding/StepWizard';
import { TargetAudienceForm } from '@/components/onboarding/TargetAudienceForm';
import { useAuth } from '@/hooks/useAuth';

export default function OnboardingStep3() {
  useAuth(); // Protect this route
  
  return (
    <div className="min-h-screen bg-brand-midnight">
      {/* Subtle aura glow */}
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />
      
      <div className="relative z-10 max-w-3xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
        {/* Back to Dashboard */}
        <Link 
          href="/dashboard" 
          className="inline-flex items-center gap-2 text-brand-silver hover:text-brand-electric transition-colors mb-6"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>Back to Dashboard</span>
        </Link>
        
        <div className="glass-card p-8">
          <h1 className="text-3xl font-heading font-bold text-white mb-2">
            Define Your Target Audience
          </h1>
          <p className="text-brand-silver/70 font-body mb-8">
            Help us understand who your brand is speaking to
          </p>

          <StepWizard currentStep={3} totalSteps={5} />

          <TargetAudienceForm />
        </div>
      </div>
    </div>
  );
}
