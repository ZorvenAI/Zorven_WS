'use client';

import { Building2, GitBranch, Package, Award } from 'lucide-react';
import { useBrandContext } from '@/hooks/useBrandContext';

const SCOPE_ICONS: Record<string, typeof Building2> = {
  parent: Building2,
  sub_brand: GitBranch,
  product_line: Package,
  endorsed: Award,
};

const SCOPE_LABELS: Record<string, string> = {
  parent: 'Parent',
  sub_brand: 'Sub-Brand',
  product_line: 'Product',
  endorsed: 'Endorsed',
};

export default function BrandContextBadge() {
  const { activeBrand, hasSubBrands } = useBrandContext();

  // Only show badge when sub-brands exist and a non-parent brand is selected
  if (!hasSubBrands || !activeBrand || activeBrand.brand_scope === 'parent') {
    return null;
  }

  const Icon = SCOPE_ICONS[activeBrand.brand_scope] ?? GitBranch;
  const label = SCOPE_LABELS[activeBrand.brand_scope] ?? activeBrand.brand_scope;

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-brand-electric/10 text-brand-electric text-[11px] font-medium">
      <Icon className="w-3 h-3" />
      <span className="truncate max-w-[100px]">{activeBrand.name}</span>
      <span className="text-brand-silver/50">&middot;</span>
      <span className="text-brand-silver/60">{label}</span>
    </span>
  );
}
