'use client';

import { useState, useEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import OptimizationDashboard from '@/components/optimization/OptimizationDashboard';

export default function OptimizationPage() {
  useAuth();

  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHasMounted(true);
  }, []);

  if (!hasMounted) {
    return (
      <div className="min-h-screen bg-brand-midnight flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-50" />

      <div className="relative z-10 max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 mb-6">
          <Link
            href="/dashboard"
            className="text-brand-silver hover:text-white transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="flex-1">
            <h1 className="text-3xl font-heading font-bold text-white">
              Optimization Command Center
            </h1>
            <p className="text-sm text-brand-silver mt-1">
              Monitor, review, and control continuous campaign optimization
            </p>
          </div>
        </div>

        <OptimizationDashboard />
      </div>
    </div>
  );
}
