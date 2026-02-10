/**
 * Tenant/workspace types for multi-tenancy support.
 */

/**
 * User role within a tenant workspace.
 */
export type TenantRole = 'owner' | 'admin' | 'editor' | 'viewer';

/**
 * Tenant info as returned from the backend JWT or API.
 */
export interface TenantInfo {
  id: number;
  name: string;
  slug: string;
  role: TenantRole;
}

/**
 * Membership record from the team management API.
 */
export interface MembershipInfo {
  id: number;
  user_id: number | null;
  user_email: string;
  role: TenantRole;
  is_active: boolean;
  accepted_at: string | null;
  invited_email: string;
}
