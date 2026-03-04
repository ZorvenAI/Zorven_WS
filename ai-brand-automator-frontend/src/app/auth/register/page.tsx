'use client';

import { Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { RegisterForm } from '@/components/auth/RegisterForm';

function RegisterContent() {
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get('invite_token') || undefined;
  const defaultEmail = searchParams.get('email') || undefined;

  return (
    <div className="relative z-10 max-w-md w-full space-y-8 px-4">
      <div className="glass-card p-8">
        <h2 className="text-center text-3xl font-heading font-bold text-white mb-2">
          Create your account
        </h2>
        <p className="text-center text-brand-silver/70 font-body mb-6">
          {inviteToken
            ? 'Create an account to accept your invitation.'
            : 'Start building your brand with AI power.'}
        </p>
        <RegisterForm inviteToken={inviteToken} defaultEmail={defaultEmail} />
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
      {/* Aura glow effect */}
      <div className="fixed inset-0 aura-glow pointer-events-none" />
      
      {/* Back to home link */}
      <Link 
        href="/" 
        className="absolute top-6 left-6 z-20 flex items-center gap-2 text-brand-silver hover:text-brand-electric transition-colors"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
        </svg>
        <span className="font-medium">Back to Home</span>
      </Link>
      
      <Suspense>
        <RegisterContent />
      </Suspense>
    </div>
  );
}