'use client';

import { useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { apiClient } from '@/lib/api';

const subscribe = () => () => {};

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const mounted = useSyncExternalStore(subscribe, () => true, () => false);
  const searchParams = useSearchParams();
  const redirectTo = searchParams.get('redirect');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const response = await apiClient.post('/auth/login/', { email, password });

      if (response.ok) {
        const data = await response.json();
        // Store tokens in localStorage
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);

        // Store tenant info if provided in login response
        if (data.tenants) {
          localStorage.setItem('tenants', JSON.stringify(data.tenants));
        }
        if (data.active_tenant_id) {
          localStorage.setItem('active_tenant_id', String(data.active_tenant_id));
        }

        // Fetch tenants from backend (in case login response omits them)
        try {
          const tenantsRes = await apiClient.get('/tenants/me/');
          if (tenantsRes.ok) {
            const tenantsList = await tenantsRes.json();
            localStorage.setItem('tenants', JSON.stringify(tenantsList));
            if (tenantsList.length > 0 && !data.active_tenant_id) {
              localStorage.setItem('active_tenant_id', String(tenantsList[0].id));
            }
          }
        } catch {
          // Non-critical — TenantProvider will retry on mount
        }

        // Redirect to original destination or dashboard
        window.location.href = redirectTo || '/dashboard';
      } else {
        let error;
        try {
          error = await response.json();
        } catch {
          error = { detail: 'Login failed' };
        }
        alert(error.detail || error.non_field_errors?.[0] || 'Login failed');
      }
    } catch (error) {
      console.error('Login error:', error);
      alert('Login failed. Please try again.');
    }
    setIsLoading(false);
  };

  if (!mounted) {
    return (
      <div className="mt-8 space-y-6">
        <div className="space-y-4">
          <div className="h-[72px]" />
          <div className="h-[72px]" />
        </div>
      </div>
    );
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
      <div className="space-y-4">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-brand-silver/70 mb-1">
            Email address
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="appearance-none relative block w-full px-4 py-3 bg-white/5 border border-white/10 placeholder-brand-silver/50 text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-electric/50 focus:border-brand-electric transition-colors sm:text-sm font-body"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-brand-silver/70 mb-1">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="appearance-none relative block w-full px-4 py-3 bg-white/5 border border-white/10 placeholder-brand-silver/50 text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-electric/50 focus:border-brand-electric transition-colors sm:text-sm font-body"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <input
            id="remember-me"
            name="remember-me"
            type="checkbox"
            className="h-4 w-4 bg-white/5 border-white/20 text-brand-electric focus:ring-brand-electric/50 rounded"
          />
          <label htmlFor="remember-me" className="ml-2 block text-sm text-brand-silver/70">
            Remember me
          </label>
        </div>

        <div className="text-sm">
          <a href="#" className="font-medium text-brand-electric hover:text-brand-electric/80 transition-colors">
            Forgot your password?
          </a>
        </div>
      </div>

      <div>
        <button
          type="submit"
          disabled={isLoading}
          className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Signing in...' : 'Sign in'}
        </button>
      </div>

      <div className="text-center">
        <Link href="/auth/register" className="font-medium text-brand-electric hover:text-brand-electric/80 transition-colors">
          Don&apos;t have an account? Sign up
        </Link>
      </div>
    </form>
  );
}