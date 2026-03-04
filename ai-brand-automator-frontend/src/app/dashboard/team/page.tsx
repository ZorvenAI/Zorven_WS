'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { useTenantContext } from '@/contexts/TenantContext';
import { useTenantRole } from '@/hooks/useTenantRole';
import { useAuth } from '@/hooks/useAuth';
import type { MembershipInfo, TenantRole } from '@/types/tenant';
import {
  Users,
  UserPlus,
  Shield,
  ChevronDown,
  Trash2,
  Mail,
  X,
} from 'lucide-react';

const subscribeNoop = () => () => {};

// ── Role helpers ──────────────────────────────────────────────────

const ROLE_OPTIONS: { value: TenantRole; label: string }[] = [
  { value: 'admin', label: 'Admin' },
  { value: 'editor', label: 'Editor' },
  { value: 'viewer', label: 'Viewer' },
];

const ROLE_COLORS: Record<TenantRole, string> = {
  owner: 'bg-amber-500/20 text-amber-400',
  admin: 'bg-brand-electric/20 text-brand-electric',
  editor: 'bg-emerald-500/20 text-emerald-400',
  viewer: 'bg-brand-silver/20 text-brand-silver/70',
};

function RoleBadge({ role }: { role: TenantRole }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${ROLE_COLORS[role]}`}
    >
      <Shield className="w-3 h-3" />
      {role}
    </span>
  );
}

// ── Invite Modal ──────────────────────────────────────────────────

function InviteModal({
  tenantId,
  onClose,
  onInvited,
}: {
  tenantId: number;
  onClose: () => void;
  onInvited: () => void;
}) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<TenantRole>('editor');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;

    setError('');
    setLoading(true);
    try {
      const res = await apiClient.post(`/tenants/${tenantId}/members/invite/`, {
        email: trimmed,
        role,
      });
      if (res.ok) {
        onInvited();
        onClose();
      } else {
        const data = await res.json();
        setError(data.error || data.detail || 'Failed to invite member');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass-card w-full max-w-md mx-4 p-6 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-brand-silver/50 hover:text-white transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-heading font-bold text-white mb-4 flex items-center gap-2">
          <UserPlus className="w-5 h-5 text-brand-electric" />
          Invite Team Member
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-brand-silver/70 mb-1">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brand-silver/50" />
              <input
                type="email"
                required
                placeholder="colleague@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-brand-silver/50 focus:outline-none focus:ring-2 focus:ring-brand-electric/50 focus:border-brand-electric"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-brand-silver/70 mb-1">
              Role
            </label>
            <div className="relative">
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as TenantRole)}
                className="w-full appearance-none px-4 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-brand-electric/50 focus:border-brand-electric"
              >
                {ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-brand-deep-navy">
                    {opt.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brand-silver/50 pointer-events-none" />
            </div>
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading || !email.trim()}
              className="flex-1 btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Sending...' : 'Send Invite'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-brand-silver/70 hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Member Row ────────────────────────────────────────────────────

function MemberRow({
  member,
  canManage,
  onRoleChange,
  onRemove,
}: {
  member: MembershipInfo;
  canManage: boolean;
  onRoleChange: (memberId: number, newRole: TenantRole) => void;
  onRemove: (memberId: number) => void;
}) {
  const displayEmail = member.user_email || member.invited_email;
  const isPending = !member.is_active;

  return (
    <div className="flex items-center gap-4 px-4 py-3 rounded-lg hover:bg-white/5 transition-colors group">
      {/* Avatar placeholder */}
      <div className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center text-sm font-medium text-brand-silver shrink-0">
        {displayEmail?.[0]?.toUpperCase() ?? '?'}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white truncate">
          {displayEmail}
          {isPending && (
            <span className="ml-2 text-[11px] text-amber-400/80 font-medium">
              Pending
            </span>
          )}
        </p>
      </div>

      {/* Role badge / selector */}
      {member.role === 'owner' || !canManage ? (
        <RoleBadge role={member.role} />
      ) : (
        <div className="relative">
          <select
            value={member.role}
            onChange={(e) =>
              onRoleChange(member.id, e.target.value as TenantRole)
            }
            className="appearance-none pl-2 pr-7 py-1 bg-white/5 border border-white/10 rounded text-xs text-brand-silver focus:outline-none focus:ring-1 focus:ring-brand-electric/50"
          >
            {ROLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} className="bg-brand-deep-navy">
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-brand-silver/50 pointer-events-none" />
        </div>
      )}

      {/* Remove button */}
      {canManage && member.role !== 'owner' && (
        <button
          onClick={() => onRemove(member.id)}
          className="opacity-0 group-hover:opacity-100 p-1.5 text-red-400/70 hover:text-red-400 hover:bg-red-500/10 rounded transition-all"
          aria-label={`Remove ${displayEmail}`}
        >
          <Trash2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

// ── Team Page ─────────────────────────────────────────────────────

export default function TeamPage() {
  useAuth();

  const { activeTenant } = useTenantContext();
  const { canManageTeam } = useTenantRole();
  const router = useRouter();

  const [members, setMembers] = useState<MembershipInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showInvite, setShowInvite] = useState(false);
  const mounted = useSyncExternalStore(subscribeNoop, () => true, () => false);

  const fetchMembers = useCallback(async () => {
    if (!activeTenant) return;
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get(`/tenants/${activeTenant.id}/members/`);
      if (res.ok) {
        const data = await res.json();
        setMembers(data);
      } else {
        setError('Failed to load team members');
      }
    } catch {
      setError('Network error loading team');
    } finally {
      setLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  const handleRoleChange = async (memberId: number, newRole: TenantRole) => {
    if (!activeTenant) return;
    try {
      const res = await apiClient.patch(`/tenants/${activeTenant.id}/members/${memberId}/`, {
        role: newRole,
      });
      if (res.ok) {
        setMembers((prev) =>
          prev.map((m) => (m.id === memberId ? { ...m, role: newRole } : m))
        );
      } else {
        const data = await res.json();
        alert(data.error || 'Failed to update role');
      }
    } catch {
      alert('Network error changing role');
    }
  };

  const handleRemove = async (memberId: number) => {
    if (!activeTenant) return;
    if (!confirm('Remove this team member?')) return;
    try {
      const res = await apiClient.delete(`/tenants/${activeTenant.id}/members/${memberId}/`);
      if (res.ok) {
        setMembers((prev) => prev.filter((m) => m.id !== memberId));
      } else {
        const data = await res.json();
        alert(data.error || 'Failed to remove member');
      }
    } catch {
      alert('Network error removing member');
    }
  };

  // Redirect if user doesn't have permission (only after client mount)
  if (mounted && !loading && !canManageTeam) {
    router.replace('/dashboard');
    return null;
  }

  if (!mounted) {
    return (
      <main className="min-h-screen bg-brand-midnight">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-heading font-bold text-white flex items-center gap-3">
                <Users className="w-7 h-7 text-brand-electric" />
                Team Members
              </h1>
            </div>
          </div>
          <div className="glass-card overflow-hidden">
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-electric" />
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-brand-midnight">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-heading font-bold text-white flex items-center gap-3">
              <Users className="w-7 h-7 text-brand-electric" />
              Team Members
            </h1>
            {mounted && activeTenant && (
              <p className="mt-1 text-sm text-brand-silver/60">
                Manage members for{' '}
                <span className="text-brand-silver">{activeTenant.name}</span>
              </p>
            )}
          </div>
          {canManageTeam && (
            <button
              onClick={() => setShowInvite(true)}
              className="btn-primary text-sm flex items-center gap-2"
            >
              <UserPlus className="w-4 h-4" />
              Invite Member
            </button>
          )}
        </div>

        {/* Content */}
        <div className="glass-card overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-electric" />
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={fetchMembers}
                className="text-sm text-brand-electric hover:underline"
              >
                Try again
              </button>
            </div>
          ) : members.length === 0 ? (
            <div className="text-center py-16">
              <Users className="w-12 h-12 mx-auto text-brand-silver/30 mb-4" />
              <p className="text-brand-silver/60">No team members yet</p>
              {canManageTeam && (
                <button
                  onClick={() => setShowInvite(true)}
                  className="mt-4 text-sm text-brand-electric hover:underline"
                >
                  Invite your first team member
                </button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {members.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  canManage={canManageTeam}
                  onRoleChange={handleRoleChange}
                  onRemove={handleRemove}
                />
              ))}
            </div>
          )}
        </div>

        {/* Team count footer */}
        {!loading && members.length > 0 && (
          <p className="mt-4 text-xs text-brand-silver/40 text-right">
            {members.length} member{members.length !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      {/* Invite modal */}
      {showInvite && activeTenant && (
        <InviteModal
          tenantId={activeTenant.id}
          onClose={() => setShowInvite(false)}
          onInvited={fetchMembers}
        />
      )}
    </main>
  );
}
