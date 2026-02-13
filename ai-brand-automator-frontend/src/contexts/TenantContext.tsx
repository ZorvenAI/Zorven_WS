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
import { apiClient } from '@/lib/api';
import type { TenantInfo } from '@/types/tenant';

interface TenantContextValue {
  /** All workspaces the user belongs to. */
  tenants: TenantInfo[];
  /** Currently active workspace (null if none). */
  activeTenant: TenantInfo | null;
  /** Switch to a different workspace. Issues new JWT tokens. */
  switchTenant: (tenantId: number) => Promise<void>;
  /** Refresh the tenants list from the backend. */
  refreshTenants: () => Promise<void>;
  /** Whether the tenants list is currently loading. */
  isLoading: boolean;
}

const TenantContext = createContext<TenantContextValue | null>(null);

// ── LocalStorage helpers ──────────────────────────────────────────

const TENANTS_KEY = 'tenants';
const ACTIVE_TENANT_KEY = 'active_tenant_id';

function loadTenants(): TenantInfo[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(TENANTS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveTenants(tenants: TenantInfo[]) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TENANTS_KEY, JSON.stringify(tenants));
}

function loadActiveTenantId(): number | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(ACTIVE_TENANT_KEY);
  return raw ? Number(raw) : null;
}

function saveActiveTenantId(id: number | null) {
  if (typeof window === 'undefined') return;
  if (id === null) {
    localStorage.removeItem(ACTIVE_TENANT_KEY);
  } else {
    localStorage.setItem(ACTIVE_TENANT_KEY, String(id));
  }
}

// ── Provider ──────────────────────────────────────────────────────

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<TenantInfo[]>(loadTenants);
  const [activeTenantId, setActiveTenantId] = useState<number | null>(
    loadActiveTenantId
  );
  const [isLoading, setIsLoading] = useState(false);

  // Derive the active tenant object
  const activeTenant = useMemo(
    () => tenants.find((t) => t.id === activeTenantId) ?? tenants[0] ?? null,
    [tenants, activeTenantId]
  );

  // Sync activeTenantId when activeTenant changes (e.g. first load)
  useEffect(() => {
    if (activeTenant && activeTenant.id !== activeTenantId) {
      setActiveTenantId(activeTenant.id);
      saveActiveTenantId(activeTenant.id);
    }
  }, [activeTenant, activeTenantId]);

  // ── Fetch tenants from backend ────────────────────────────────

  const refreshTenants = useCallback(async () => {
    const token =
      typeof window !== 'undefined'
        ? localStorage.getItem('access_token')
        : null;
    if (!token) return;

    setIsLoading(true);
    try {
      const response = await apiClient.get('/tenants/me/');
      if (response.ok) {
        const data: TenantInfo[] = await response.json();
        setTenants(data);
        saveTenants(data);

        // If no active tenant set, default to the first
        if (!activeTenantId && data.length > 0) {
          setActiveTenantId(data[0].id);
          saveActiveTenantId(data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch tenants:', err);
    } finally {
      setIsLoading(false);
    }
  }, [activeTenantId]);

  // ── Switch workspace ──────────────────────────────────────────

  const switchTenant = useCallback(
    async (tenantId: number) => {
      if (tenantId === activeTenantId) return;

      setIsLoading(true);
      try {
        const response = await apiClient.post('/tenants/switch/', {
          tenant_id: tenantId,
        });

        if (response.ok) {
          const data = await response.json();

          // Store new tokens
          localStorage.setItem('access_token', data.tokens.access);
          localStorage.setItem('refresh_token', data.tokens.refresh);

          // Update active tenant
          setActiveTenantId(tenantId);
          saveActiveTenantId(tenantId);

          // Update the tenants list in case roles changed
          await refreshTenants();

          // Reload the page to reset all component state
          window.location.reload();
        } else {
          const err = await response.json();
          throw new Error(err.error || 'Failed to switch workspace');
        }
      } catch (err) {
        console.error('Tenant switch failed:', err);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [activeTenantId, refreshTenants]
  );

  // ── Initial load ──────────────────────────────────────────────

  useEffect(() => {
    refreshTenants();
  }, [refreshTenants]);

  const value = useMemo<TenantContextValue>(
    () => ({
      tenants,
      activeTenant,
      switchTenant,
      refreshTenants,
      isLoading,
    }),
    [tenants, activeTenant, switchTenant, refreshTenants, isLoading]
  );

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────

export function useTenantContext(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error('useTenantContext must be used within a TenantProvider');
  }
  return ctx;
}
