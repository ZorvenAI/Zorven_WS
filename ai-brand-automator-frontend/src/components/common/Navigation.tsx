'use client';

import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useState, useSyncExternalStore, useEffect } from 'react';

// External store for localStorage token
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

export function Navigation() {
  const router = useRouter();
  const pathname = usePathname();
  const token = useSyncExternalStore(subscribeToToken, getTokenSnapshot, getServerSnapshot);
  const [, forceUpdate] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  
  // Derive login state from token
  const isLoggedIn = !!token;

  // Close mobile menu when route changes
  useEffect(() => {
    // Use requestAnimationFrame to avoid synchronous setState in effect
    requestAnimationFrame(() => setMobileMenuOpen(false));
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('company_id');
    forceUpdate(n => n + 1); // Trigger re-render after logout
    setMobileMenuOpen(false);
    router.push('/auth/login');
  };

  // Don't show navigation on auth pages
  if (pathname?.startsWith('/auth/')) {
    return null;
  }

  const navLinks = [
    { href: '/dashboard', label: 'Dashboard', active: pathname === '/dashboard' },
    { href: '/onboarding', label: 'Onboarding', active: pathname?.startsWith('/onboarding') },
    { href: '/chat', label: 'Chat', active: pathname === '/chat' },
    { href: '/files', label: 'Files', active: pathname === '/files' },
    { href: '/automation', label: 'Automation', active: pathname === '/automation' },
  ];

  return (
    <nav className="nav-dark relative z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex-shrink-0 flex items-center">
              <span className="text-lg sm:text-2xl font-heading font-bold text-brand-electric">AI Brand Automator</span>
            </Link>
            
            {/* Desktop Navigation */}
            {isLoggedIn && (
              <div className="hidden md:ml-10 md:flex md:space-x-8">
                {navLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors ${
                      link.active
                        ? 'border-brand-electric text-white'
                        : 'border-transparent text-brand-silver/70 hover:border-brand-ghost hover:text-white'
                    }`}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Desktop Logout/Login */}
            {isLoggedIn ? (
              <button
                onClick={handleLogout}
                className="hidden sm:block text-sm text-brand-silver/70 hover:text-brand-electric transition-colors px-3 py-1.5 rounded-md hover:bg-white/5"
              >
                Logout
              </button>
            ) : (
              <Link
                href="/auth/login"
                className="btn-primary text-sm"
              >
                Login
              </Link>
            )}

            {/* Mobile Menu Button */}
            {isLoggedIn && (
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden inline-flex items-center justify-center p-2 rounded-md text-brand-silver hover:text-white hover:bg-white/10 transition-colors"
                aria-expanded={mobileMenuOpen}
                aria-label="Toggle navigation menu"
              >
                {mobileMenuOpen ? (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {isLoggedIn && mobileMenuOpen && (
        <div className="md:hidden absolute top-16 left-0 right-0 bg-brand-midnight/95 backdrop-blur-lg border-b border-white/10 shadow-xl">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`block px-4 py-3 rounded-lg text-base font-medium transition-colors ${
                  link.active
                    ? 'bg-brand-electric/20 text-brand-electric'
                    : 'text-brand-silver hover:bg-white/10 hover:text-white'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="border-t border-white/10 mt-2 pt-2">
              <button
                onClick={handleLogout}
                className="w-full text-left px-4 py-3 rounded-lg text-base font-medium text-red-400 hover:bg-red-500/10 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
