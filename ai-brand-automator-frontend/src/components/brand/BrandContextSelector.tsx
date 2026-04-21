'use client';

import { useState, useRef, useEffect } from 'react';
import { Building2, GitBranch, Package, Award, ChevronDown } from 'lucide-react';
import { useBrandContext } from '@/hooks/useBrandContext';

const SCOPE_ICONS: Record<string, typeof Building2> = {
  parent: Building2,
  sub_brand: GitBranch,
  product_line: Package,
  endorsed: Award,
};

const SCOPE_LABELS: Record<string, string> = {
  parent: 'Parent Brand',
  sub_brand: 'Sub-Brand',
  product_line: 'Product Line',
  endorsed: 'Endorsed',
};

export default function BrandContextSelector() {
  const { brands, activeBrand, switchBrand, isLoading, hasSubBrands } =
    useBrandContext();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClick);
      return () => document.removeEventListener('mousedown', handleClick);
    }
  }, [open]);

  // Hidden when only parent brand exists (no BAA run yet)
  if (!hasSubBrands) return null;

  const Icon = SCOPE_ICONS[activeBrand?.brand_scope ?? 'parent'] ?? Building2;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        disabled={isLoading}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-colors text-sm disabled:opacity-50"
      >
        <Icon className="w-3.5 h-3.5 text-brand-electric" />
        <span className="text-brand-silver max-w-[140px] truncate">
          {activeBrand?.name ?? 'Select Brand'}
        </span>
        <ChevronDown
          className={`w-3 h-3 text-brand-silver/60 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-1 z-50 min-w-[200px] max-w-[280px] rounded-lg bg-brand-midnight border border-white/10 shadow-xl overflow-hidden">
          {brands.map((brand) => {
            const BIcon = SCOPE_ICONS[brand.brand_scope] ?? Building2;
            const isActive =
              brand.brand_context_id === activeBrand?.brand_context_id;

            return (
              <button
                key={brand.brand_context_id}
                onClick={() => {
                  switchBrand(brand.brand_context_id);
                  setOpen(false);
                }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-electric/10 text-white'
                    : 'text-brand-silver hover:bg-white/5 hover:text-white'
                }`}
              >
                <BIcon
                  className={`w-3.5 h-3.5 shrink-0 ${
                    isActive ? 'text-brand-electric' : 'text-brand-silver/50'
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="break-words">{brand.name}</div>
                  <div className="text-[10px] text-brand-silver/50">
                    {SCOPE_LABELS[brand.brand_scope] ?? brand.brand_scope}
                  </div>
                </div>
                {isActive && (
                  <div className="w-1.5 h-1.5 rounded-full bg-brand-electric shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
