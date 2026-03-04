'use client';

import { OverviewCards } from '@/components/dashboard/OverviewCards';
import RecentActivity from '@/components/dashboard/RecentActivity';
import { QuickActions } from '@/components/dashboard/QuickActions';
import SocialAnalytics from '@/components/dashboard/SocialAnalytics';
import { useAuth } from '@/hooks/useAuth';

export default function DashboardPage() {
  useAuth(); // Protect this route
  return (
    <div className="min-h-screen bg-brand-midnight">
      {/* Subtle aura glow */}
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-50" />
      
      <div className="relative z-10 max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-heading font-bold text-white mb-8">Dashboard</h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <OverviewCards />
            
            {/* Social Analytics Section */}
            <div className="mt-6">
              <h2 className="text-xl font-heading font-semibold text-white mb-4">Social Media Analytics</h2>
              <SocialAnalytics />
            </div>
            
            <div className="mt-6">
              <RecentActivity />
            </div>
          </div>
          <div>
            <QuickActions />
          </div>
        </div>
      </div>
    </div>
  );
}