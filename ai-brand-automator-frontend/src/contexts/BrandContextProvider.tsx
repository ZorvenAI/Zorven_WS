'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { getBrandContextOptions } from '@/lib/brand-context';
import { useTenantContext } from '@/contexts/TenantContext';
import type { BrandContextEntry } from '@/types/brand-context';

interface BrandContextValue {
  /** All available brand entities (parent + sub-brands). */
  brands: BrandContextEntry[];
  /** Currently active brand (null = parent/default). */
  activeBrand: BrandContextEntry | null;
  /** Switch to a different brand context. */
  switchBrand: (brandContextId: string) => void;
  /** Whether brand options are loading. */
  isLoading: boolean;
  /** Convenience: true when sub-brands exist (brands.length > 1). */
  hasSubBrands: boolean;
  /** Refresh brand options from backend. */
  refreshBrands: () => Promise<void>;
}

const BrandContext = createContext<BrandContextValue | null>(null);

const STORAGE_PREFIX = 'brand_context_';

function loadActiveBrandId(tenantId: number | null): string {
  if (typeof window === 'undefined' || !tenantId) return 'parent';
  return localStorage.getItem(`${STORAGE_PREFIX}${tenantId}`) || 'parent';
}

function saveActiveBrandId(tenantId: number | null, brandId: string) {
  if (typeof window === 'undefined' || !tenantId) return;
  localStorage.setItem(`${STORAGE_PREFIX}${tenantId}`, brandId);
}

export function BrandContextProvider({ children }: { children: ReactNode }) {
  const { activeTenant } = useTenantContext();
  const tenantId = activeTenant?.id ?? null;

  const [brands, setBrands] = useState<BrandContextEntry[]>([]);
  const [activeBrandId, setActiveBrandId] = useState<string>(() =>
    loadActiveBrandId(tenantId)
  );
  const [isLoading, setIsLoading] = useState(false);

  const activeBrand = useMemo(() => {
    if (brands.length === 0) return null;
    const found = brands.find((b) => b.brand_context_id === activeBrandId);
    return found ?? brands[0] ?? null;
  }, [brands, activeBrandId]);

  const hasSubBrands = brands.length > 1;

  const refreshBrands = useCallback(async () => {
    setIsLoading(true);
    try {
      const options = await getBrandContextOptions();
      setBrands(options);
    } catch {
      setBrands([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const switchBrand = useCallback(
    (brandContextId: string) => {
      setActiveBrandId(brandContextId);
      saveActiveBrandId(tenantId, brandContextId);
    },
    [tenantId]
  );

  // Re-fetch when tenant changes
  useEffect(() => {
    if (tenantId) {
      setActiveBrandId(loadActiveBrandId(tenantId));
      refreshBrands();
    } else {
      setBrands([]);
    }
  }, [tenantId, refreshBrands]);

  const value = useMemo<BrandContextValue>(
    () => ({
      brands,
      activeBrand,
      switchBrand,
      isLoading,
      hasSubBrands,
      refreshBrands,
    }),
    [brands, activeBrand, switchBrand, isLoading, hasSubBrands, refreshBrands]
  );

  return (
    <BrandContext.Provider value={value}>{children}</BrandContext.Provider>
  );
}

export function useBrandContext(): BrandContextValue {
  const ctx = useContext(BrandContext);
  if (!ctx) {
    throw new Error(
      'useBrandContext must be used within a BrandContextProvider'
    );
  }
  return ctx;
}
