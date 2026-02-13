'use client';

import { useMemo } from 'react';
import { useTenantContext } from '@/contexts/TenantContext';
import type { TenantRole } from '@/types/tenant';

interface TenantRoleInfo {
  /** Current role in the active workspace. */
  role: TenantRole | undefined;
  /** True if the user is the workspace owner. */
  isOwner: boolean;
  /** True if the user is owner or admin. */
  isAdmin: boolean;
  /** True if the user can edit content (owner/admin/editor). */
  canEdit: boolean;
  /** True if the user can manage team members (owner/admin). */
  canManageTeam: boolean;
  /** True if only the owner can manage billing. */
  canManageBilling: boolean;
}

/**
 * Hook that derives role-based permission flags from the active tenant.
 *
 * Usage:
 * ```tsx
 * const { canEdit, canManageTeam } = useTenantRole();
 * if (!canEdit) return <p>Read-only access</p>;
 * ```
 */
export function useTenantRole(): TenantRoleInfo {
  const { activeTenant } = useTenantContext();

  return useMemo(() => {
    const role = activeTenant?.role;
    return {
      role,
      isOwner: role === 'owner',
      isAdmin: role === 'owner' || role === 'admin',
      canEdit: role === 'owner' || role === 'admin' || role === 'editor',
      canManageTeam: role === 'owner' || role === 'admin',
      canManageBilling: role === 'owner',
    };
  }, [activeTenant?.role]);
}
