'use client';

import { ReactNode } from 'react';
import { TenantProvider } from '@/contexts/TenantContext';
import { Navigation } from '@/components/common/Navigation';
import { ToastContainer } from '@/components/common/ToastContainer';

export function ClientLayout({ children }: { children: ReactNode }) {
  return (
    <TenantProvider>
      <Navigation>{children}</Navigation>
      <ToastContainer />
    </TenantProvider>
  );
}
