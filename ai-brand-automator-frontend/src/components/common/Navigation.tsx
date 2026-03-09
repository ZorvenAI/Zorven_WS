'use client';

import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useState, useSyncExternalStore, useEffect, useCallback } from 'react';
import {
  LayoutDashboard,
  Compass,
  MessageSquare,
  FolderOpen,
  Zap,
  GitBranch,
  Bot,
  BarChart3,
  Users,
  CreditCard,
  PanelLeftClose,
  PanelLeft,
  Menu,
  X,
  LogOut,
} from 'lucide-react';
import { WorkspaceSwitcher } from '@/components/layout/WorkspaceSwitcher';
import { useTenantRole } from '@/hooks/useTenantRole';

// ── Auth token store ──

function subscribeToToken(callback: () => void) {
  window.addEventListener('storage', callback);
  return () => window.removeEventListener('storage', callback);
}

function getTokenSnapshot() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('access_token');
}

function getServerSnapshot() {
  return null;
}

// ── Sidebar collapsed state (localStorage) ──

function readCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  return localStorage.getItem('sidebar_collapsed') === '1';
}

// ── Types ──

interface NavLink {
  href: string;
  label: string;
  icon: React.ReactNode;
  active: boolean;
}

// ── Main component ──

export function Navigation({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const token = useSyncExternalStore(subscribeToToken, getTokenSnapshot, getServerSnapshot);
  const [, forceUpdate] = useState(0);
  const { canManageTeam, canManageBilling, canEdit: canEditFlag } = useTenantRole();

  const isLoggedIn = !!token;

  // Sidebar state
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hasMounted, setHasMounted] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  // Read persisted state on mount (requestAnimationFrame avoids sync setState in effect)
  useEffect(() => {
    requestAnimationFrame(() => {
      setCollapsed(readCollapsed());
      setHasMounted(true);
    });
  }, []);

  // Close mobile sidebar on route change
  useEffect(() => {
    requestAnimationFrame(() => setMobileOpen(false));
  }, [pathname]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('sidebar_collapsed', next ? '1' : '0');
      return next;
    });
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('company_id');
    localStorage.removeItem('tenants');
    localStorage.removeItem('active_tenant_id');
    forceUpdate((n) => n + 1);
    setMobileOpen(false);
    router.push('/auth/login');
  };

  // On auth pages and public tool pages, render children without shell
  if (pathname?.startsWith('/auth/') || pathname === '/brand-equity') {
    return <>{children}</>;
  }

  // Icon size for nav links
  const iconCls = 'w-5 h-5 shrink-0';

  // Guard role-dependent flags behind hasMounted to prevent hydration mismatches
  const canEdit = hasMounted ? canEditFlag : false;
  const canTeam = hasMounted ? canManageTeam : false;
  const canBilling = hasMounted ? canManageBilling : false;

  const navLinks: NavLink[] = [
    ...(canEdit
      ? [{ href: '/chat', label: 'AI Chat', icon: <MessageSquare className={iconCls} />, active: pathname === '/chat' }]
      : []),
    { href: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard className={iconCls} />, active: pathname === '/dashboard' },
    ...(canEdit
      ? [{ href: '/onboarding', label: 'Onboarding', icon: <Compass className={iconCls} />, active: pathname?.startsWith('/onboarding') ?? false }]
      : []),
    { href: '/files', label: 'Files', icon: <FolderOpen className={iconCls} />, active: pathname === '/files' },
    { href: '/automation', label: 'Automation', icon: <Zap className={iconCls} />, active: pathname === '/automation' },
    { href: '/dashboard/pipelines', label: 'Pipelines', icon: <GitBranch className={iconCls} />, active: pathname?.startsWith('/dashboard/pipelines') ?? false },
    ...(canEdit
      ? [{ href: '/dashboard/ai-assistant', label: 'AI Assistant', icon: <Bot className={iconCls} />, active: pathname?.startsWith('/dashboard/ai-assistant') ?? false }]
      : []),
    { href: '/dashboard/analysis', label: 'Reports', icon: <BarChart3 className={iconCls} />, active: pathname?.startsWith('/dashboard/analysis') ?? false },
    ...(canTeam
      ? [{ href: '/dashboard/team', label: 'Team', icon: <Users className={iconCls} />, active: pathname === '/dashboard/team' }]
      : []),
    ...(canBilling
      ? [{ href: '/billing', label: 'Billing', icon: <CreditCard className={iconCls} />, active: pathname === '/billing' }]
      : []),
  ];

  // Sidebar width classes
  const sidebarW = collapsed ? 'w-16' : 'w-56';
  const contentPl = collapsed ? 'md:pl-16' : 'md:pl-56';

  return (
    <>
      {/* ── Fixed top bar ── */}
      <header className="fixed top-0 left-0 right-0 h-14 z-40 nav-dark flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          {/* Mobile hamburger */}
          {isLoggedIn && (
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-1.5 rounded-md text-brand-silver hover:text-white hover:bg-white/10 transition-colors"
              aria-label="Toggle sidebar"
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          )}

          {/* Logo */}
          <Link href="/" className="flex items-center">
            <span className="text-lg font-heading font-bold text-brand-electric">
              AI Brand Automator
            </span>
          </Link>
        </div>

        <div className="flex items-center gap-3">
          {/* Workspace Switcher */}
          {isLoggedIn && hasMounted && <WorkspaceSwitcher />}

          {/* Logout / Login */}
          {isLoggedIn ? (
            <button
              onClick={() => setShowLogoutConfirm(true)}
              className="hidden sm:flex items-center gap-1.5 text-sm text-brand-silver/70 hover:text-brand-electric transition-colors px-2 py-1.5 rounded-md hover:bg-white/5"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden lg:inline">Logout</span>
            </button>
          ) : (
            <Link href="/auth/login" className="btn-primary text-sm">
              Login
            </Link>
          )}
        </div>
      </header>

      {/* ── Mobile backdrop ── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      {isLoggedIn && (
        <aside
          className={`
            fixed top-14 bottom-0 z-30 sidebar-nav
            flex flex-col
            transition-all duration-300 ease-in-out
            ${/* Desktop: always visible, respects collapsed */ ''}
            hidden md:flex ${sidebarW}
            ${/* Mobile: overlay, always expanded width */ ''}
            ${mobileOpen ? '!flex w-56 shadow-2xl' : ''}
          `}
        >
          {/* Nav links */}
          <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                title={collapsed && !mobileOpen ? link.label : undefined}
                onClick={() => setMobileOpen(false)}
                className={`
                  flex items-center gap-3 rounded-lg px-3 py-2.5
                  text-sm font-medium transition-colors
                  ${link.active
                    ? 'bg-brand-electric/10 text-brand-electric border-l-2 border-brand-electric -ml-0.5 pl-[10px]'
                    : 'text-brand-silver/70 hover:bg-white/5 hover:text-white'
                  }
                `}
              >
                {link.icon}
                {(!collapsed || mobileOpen) && (
                  <span className="truncate">{link.label}</span>
                )}
              </Link>
            ))}
          </nav>

          {/* Collapse toggle (desktop only) */}
          <div className="hidden md:block border-t border-white/8 p-2">
            <button
              onClick={toggleCollapsed}
              className="flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-sm text-brand-silver/50 hover:text-white hover:bg-white/5 transition-colors"
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? (
                <PanelLeft className="w-5 h-5 shrink-0" />
              ) : (
                <>
                  <PanelLeftClose className="w-5 h-5 shrink-0" />
                  <span className="truncate">Collapse</span>
                </>
              )}
            </button>
          </div>

          {/* Mobile logout */}
          {mobileOpen && (
            <div className="md:hidden border-t border-white/8 p-2">
              <button
                onClick={() => setShowLogoutConfirm(true)}
                className="flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <LogOut className="w-5 h-5 shrink-0" />
                <span>Logout</span>
              </button>
            </div>
          )}
        </aside>
      )}

      {/* ── Content area ── */}
      <div
        className={`
          pt-14 min-h-screen
          transition-all duration-300 ease-in-out
          ${isLoggedIn ? contentPl : ''}
        `}
      >
        {children}
      </div>

      {/* ── Logout confirmation dialog ── */}
      {showLogoutConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowLogoutConfirm(false)}
        >
          <div
            className="glass-card p-6 w-full max-w-sm mx-4 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-heading font-semibold text-white">
              Confirm Logout
            </h3>
            <p className="text-sm text-brand-silver/70">
              Are you sure you want to logout? You will need to sign in again to access your account.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="px-4 py-2 text-sm text-brand-silver/70 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowLogoutConfirm(false);
                  handleLogout();
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-500/80 hover:bg-red-500 rounded-lg transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
