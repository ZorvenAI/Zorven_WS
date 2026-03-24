'use client';

import { ReactNode } from 'react';
import { TenantProvider } from '@/contexts/TenantContext';
import { BrandContextProvider } from '@/contexts/BrandContextProvider';
import { Navigation } from '@/components/common/Navigation';
import { ToastContainer } from '@/components/common/ToastContainer';

export function ClientLayout({ children }: { children: ReactNode }) {
  return (
    <TenantProvider>
      <BrandContextProvider>
        <Navigation>{children}</Navigation>
        <ToastContainer />
      </BrandContextProvider>
    </TenantProvider>
  );
}
