'use client';

import { useState, useEffect, useRef } from 'react';
import { Zap, X } from 'lucide-react';
import { OverviewCards } from '@/components/dashboard/OverviewCards';
import RecentActivity from '@/components/dashboard/RecentActivity';
import { QuickActions } from '@/components/dashboard/QuickActions';
import SocialAnalytics from '@/components/dashboard/SocialAnalytics';
import AnalyticsDashboard from '@/components/analytics/AnalyticsDashboard';
import { useAuth } from '@/hooks/useAuth';

export default function DashboardPage() {
  useAuth(); // Protect this route
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close drawer on click outside
  useEffect(() => {
    if (!drawerOpen) return;
    function handleClick(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setDrawerOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [drawerOpen]);

  // Close drawer on Escape key
  useEffect(() => {
    if (!drawerOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setDrawerOpen(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [drawerOpen]);

  return (
    <div className="min-h-screen bg-brand-midnight">
      {/* Subtle aura glow */}
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-50" />

      <div className="relative z-10 max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-heading font-bold text-white mb-8">Dashboard</h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <OverviewCards />

            {/* Workflow Analytics Section */}
            <div className="mt-6">
              <AnalyticsDashboard />
            </div>

            <div className="mt-6">
              <RecentActivity />
            </div>
          </div>
          <div>
            {/* Social Analytics moved to right column */}
            <h2 className="text-xl font-heading font-semibold text-white mb-4">Social Media Analytics</h2>
            <SocialAnalytics />
          </div>
        </div>
      </div>

      {/* Quick Actions retractable tab */}
      <button
        onClick={() => setDrawerOpen((prev) => !prev)}
        className={`fixed top-1/2 -translate-y-1/2 z-40 flex items-center gap-1.5 px-2 py-3 rounded-l-lg border border-r-0 border-white/10 transition-all duration-300 ${
          drawerOpen
            ? 'right-[320px] bg-brand-electric/20 text-brand-electric border-brand-electric/30'
            : 'right-0 bg-brand-midnight/90 text-brand-silver hover:text-brand-electric hover:bg-white/5'
        }`}
        title="Quick Actions"
      >
        <Zap className="h-4 w-4" />
        <span className="text-xs font-medium [writing-mode:vertical-lr] rotate-180">
          Actions
        </span>
      </button>

      {/* Backdrop overlay */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px] lg:hidden" />
      )}

      {/* Quick Actions slide-out drawer */}
      <div
        ref={drawerRef}
        className={`fixed top-0 right-0 z-50 h-full w-[320px] bg-brand-midnight/95 backdrop-blur-md border-l border-white/10 shadow-2xl transition-transform duration-300 ease-in-out ${
          drawerOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h2 className="text-lg font-heading font-semibold text-white">Quick Actions</h2>
          <button
            onClick={() => setDrawerOpen(false)}
            className="text-brand-silver/60 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto h-[calc(100%-64px)] p-4">
          <QuickActions />
        </div>
      </div>
    </div>
  );
}