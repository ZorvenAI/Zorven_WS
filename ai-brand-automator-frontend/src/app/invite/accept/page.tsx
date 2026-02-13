'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { env } from '@/lib/env';
import { useTenantContext } from '@/contexts/TenantContext';
import { Mail, Users, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

type InviteInfo = {
  email: string;
  tenant_name: string;
  role: string;
  inviter_name: string;
  has_account?: boolean;
};

type AcceptResult = {
  tenant: {
    id: number;
    name: string;
    slug: string;
    role: string;
  };
};

function AcceptInviteContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const { refreshTenants } = useTenantContext();

  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    setIsLoggedIn(!!localStorage.getItem('access_token'));
  }, []);

  const fetchInvite = useCallback(async () => {
    if (!token) {
      setError('No invitation token provided.');
      setLoading(false);
      return;
    }
    try {
      // Use plain fetch (not apiClient) because this must work for
      // unauthenticated users — apiClient auto-redirects on 401.
      const url = env.getApiUrl(
        `/tenants/invite/accept/?token=${encodeURIComponent(token)}`
      );
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        const data: InviteInfo = await res.json();
        setInvite(data);
      } else {
        const data = await res.json();
        setError(data.error || 'Invalid or expired invitation.');
      }
    } catch {
      setError('Failed to load invitation details.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchInvite();
  }, [fetchInvite]);

  const handleAccept = async () => {
    if (!token) return;
    setAccepting(true);
    setError('');

    try {
      const res = await apiClient.post('/tenants/invite/accept/', { token });
      if (res.ok) {
        const data: AcceptResult = await res.json();
        setAccepted(true);

        // Refresh tenants in context and switch to the new workspace
        await refreshTenants();

        // Store the new active tenant and redirect
        localStorage.setItem('active_tenant_id', String(data.tenant.id));
        setTimeout(() => {
          window.location.href = '/dashboard';
        }, 1500);
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to accept invitation.');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setAccepting(false);
    }
  };

  // ── Loading state ──
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
        <div className="fixed inset-0 aura-glow pointer-events-none" />
        <div className="relative z-10">
          <Loader2 className="w-8 h-8 text-brand-electric animate-spin" />
        </div>
      </div>
    );
  }

  // ── Error state (no valid invite) ──
  if (error && !invite) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
        <div className="fixed inset-0 aura-glow pointer-events-none" />
        <div className="relative z-10 max-w-md w-full px-4">
          <div className="glass-card p-8 text-center">
            <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <h2 className="text-xl font-heading font-bold text-white mb-2">
              Invalid Invitation
            </h2>
            <p className="text-brand-silver/70 mb-6">{error}</p>
            <Link
              href="/auth/login"
              className="btn-primary inline-block text-sm"
            >
              Go to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Accepted state ──
  if (accepted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
        <div className="fixed inset-0 aura-glow pointer-events-none" />
        <div className="relative z-10 max-w-md w-full px-4">
          <div className="glass-card p-8 text-center">
            <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
            <h2 className="text-xl font-heading font-bold text-white mb-2">
              Invitation Accepted!
            </h2>
            <p className="text-brand-silver/70">
              You&apos;ve joined{' '}
              <span className="text-white font-medium">
                {invite?.tenant_name}
              </span>
              . Redirecting to dashboard...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── Invite preview ──
  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none" />
      <Link
        href="/"
        className="absolute top-6 left-6 z-20 flex items-center gap-2 text-brand-silver hover:text-brand-electric transition-colors"
      >
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 19l-7-7m0 0l7-7m-7 7h18"
          />
        </svg>
        <span className="font-medium">Back to Home</span>
      </Link>

      <div className="relative z-10 max-w-md w-full px-4">
        <div className="glass-card p-8">
          {/* Header */}
          <div className="text-center mb-6">
            <div className="w-14 h-14 rounded-full bg-brand-electric/20 flex items-center justify-center mx-auto mb-4">
              <Mail className="w-7 h-7 text-brand-electric" />
            </div>
            <h2 className="text-2xl font-heading font-bold text-white mb-1">
              You&apos;re Invited
            </h2>
            <p className="text-brand-silver/70 text-sm">
              You&apos;ve been invited to join a workspace
            </p>
          </div>

          {/* Invite details */}
          <div className="bg-white/5 rounded-lg p-4 mb-6 space-y-3">
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-brand-silver/50 shrink-0" />
              <div>
                <p className="text-xs text-brand-silver/50">Workspace</p>
                <p className="text-sm text-white font-medium">
                  {invite?.tenant_name}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Mail className="w-5 h-5 text-brand-silver/50 shrink-0" />
              <div>
                <p className="text-xs text-brand-silver/50">Invited by</p>
                <p className="text-sm text-white font-medium">
                  {invite?.inviter_name || 'A team admin'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <CheckCircle className="w-5 h-5 text-brand-silver/50 shrink-0" />
              <div>
                <p className="text-xs text-brand-silver/50">Your role</p>
                <p className="text-sm text-white font-medium capitalize">
                  {invite?.role}
                </p>
              </div>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400 text-center mb-4">{error}</p>
          )}

          {/* Action buttons */}
          {isLoggedIn ? (
            <button
              onClick={handleAccept}
              disabled={accepting}
              className="w-full btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {accepting ? 'Accepting...' : 'Accept Invitation'}
            </button>
          ) : (
            <div className="space-y-3">
              <p className="text-center text-sm text-brand-silver/70">
                {invite?.has_account
                  ? 'Sign in to accept this invitation.'
                  : 'Sign in or create an account to accept this invitation.'}
              </p>
              <Link
                href={`/auth/login?redirect=${encodeURIComponent(`/invite/accept?token=${token}`)}`}
                className="w-full btn-primary text-sm text-center block"
              >
                Sign In to Accept
              </Link>
              {!invite?.has_account && (
                <Link
                  href={`/auth/register?invite_token=${encodeURIComponent(token || '')}&email=${encodeURIComponent(invite?.email || '')}`}
                  className="w-full block text-center text-sm text-brand-electric hover:underline py-2"
                >
                  Create an Account
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-brand-midnight">
          <Loader2 className="w-8 h-8 text-brand-electric animate-spin" />
        </div>
      }
    >
      <AcceptInviteContent />
    </Suspense>
  );
}
