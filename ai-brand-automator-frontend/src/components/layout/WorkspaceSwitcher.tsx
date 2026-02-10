'use client';

import { useState, useRef, useEffect } from 'react';
import { useTenantContext } from '@/contexts/TenantContext';
import { ChevronDown, Check, Plus, Building2 } from 'lucide-react';
import type { TenantRole } from '@/types/tenant';

/** Compact role badge for the dropdown list. */
function RoleBadge({ role }: { role: TenantRole }) {
  const colors: Record<TenantRole, string> = {
    owner: 'bg-amber-500/20 text-amber-400',
    admin: 'bg-brand-electric/20 text-brand-electric',
    editor: 'bg-emerald-500/20 text-emerald-400',
    viewer: 'bg-brand-silver/20 text-brand-silver/70',
  };

  return (
    <span
      className={`ml-auto text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${colors[role]}`}
    >
      {role}
    </span>
  );
}

export function WorkspaceSwitcher() {
  const { tenants, activeTenant, switchTenant, isLoading } =
    useTenantContext();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [brandName, setBrandName] = useState('');
  const [createError, setCreateError] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
        setBrandName('');
        setCreateError('');
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close on Escape
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        setCreating(false);
        setBrandName('');
        setCreateError('');
      }
    }
    if (open) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [open]);

  const handleSwitch = async (tenantId: number) => {
    setOpen(false);
    try {
      await switchTenant(tenantId);
    } catch {
      // switchTenant already logs the error
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = brandName.trim();
    if (!trimmed) return;

    setCreateError('');
    try {
      const { apiClient } = await import('@/lib/api');
      const res = await apiClient.post('/tenants/create/', {
        name: trimmed,
      });

      if (res.ok) {
        const data = await res.json();
        setCreating(false);
        setBrandName('');
        // Switch to the newly created workspace
        await switchTenant(data.id);
      } else {
        const err = await res.json();
        setCreateError(err.error || err.detail || 'Failed to create workspace');
      }
    } catch {
      setCreateError('Network error. Please try again.');
    }
  };

  if (!activeTenant) return null;

  return (
    <div className="relative" ref={menuRef}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(!open)}
        disabled={isLoading}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm text-white transition-colors disabled:opacity-50"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Building2 className="w-4 h-4 text-brand-electric" />
        <span className="max-w-[140px] truncate font-medium">
          {activeTenant.name}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-brand-silver/70 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full mt-2 w-72 rounded-xl bg-brand-deep-navy border border-white/10 shadow-2xl backdrop-blur-xl z-[60] overflow-hidden">
          {/* Workspace list */}
          <div className="p-2 max-h-60 overflow-y-auto">
            <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-brand-silver/50">
              Workspaces
            </p>
            {tenants.map((t) => (
              <button
                key={t.id}
                onClick={() => handleSwitch(t.id)}
                disabled={t.id === activeTenant.id || isLoading}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  t.id === activeTenant.id
                    ? 'bg-brand-electric/10 text-white cursor-default'
                    : 'text-brand-silver hover:bg-white/5 hover:text-white'
                }`}
              >
                <Building2 className="w-4 h-4 shrink-0 text-brand-silver/50" />
                <span className="truncate">{t.name}</span>
                {t.id === activeTenant.id && (
                  <Check className="w-4 h-4 ml-auto text-brand-electric shrink-0" />
                )}
                {t.id !== activeTenant.id && <RoleBadge role={t.role} />}
              </button>
            ))}
          </div>

          {/* Separator */}
          <div className="border-t border-white/10" />

          {/* Create new workspace */}
          {creating ? (
            <form onSubmit={handleCreate} className="p-3 space-y-2">
              <input
                type="text"
                placeholder="Brand name"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                autoFocus
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-brand-silver/50 focus:outline-none focus:ring-2 focus:ring-brand-electric/50 focus:border-brand-electric"
              />
              {createError && (
                <p className="text-xs text-red-400">{createError}</p>
              )}
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={!brandName.trim()}
                  className="flex-1 btn-primary text-xs py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setBrandName('');
                    setCreateError('');
                  }}
                  className="px-3 py-1.5 text-xs text-brand-silver/70 hover:text-white transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button
              onClick={() => setCreating(true)}
              className="w-full flex items-center gap-2 px-5 py-3 text-sm text-brand-electric hover:bg-white/5 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create New Brand
            </button>
          )}
        </div>
      )}
    </div>
  );
}
