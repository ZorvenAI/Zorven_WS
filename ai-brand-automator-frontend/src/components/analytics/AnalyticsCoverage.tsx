'use client';

import { BarChart3 } from 'lucide-react';
import type { AnalyticsCoverage as CoverageData } from '@/types/analytics';
import Tooltip from '@/components/ui/Tooltip';

interface AnalyticsCoverageProps {
  data: CoverageData | null;
}

export default function AnalyticsCoverage({ data }: AnalyticsCoverageProps) {
  if (!data || data.total_jobs === 0) return null;

  return (
    <Tooltip tabIndex={0} text="How many completed workflows had metrics successfully extracted. Excluded workflows may have failed extraction or lacked extractable data.">
      <div className="flex items-center gap-2 text-xs text-brand-silver">
        <BarChart3 className="h-3.5 w-3.5" />
        <span>
          {data.analytics_jobs} of {data.total_jobs} workflows analyzed
          ({data.coverage_pct}%)
        </span>
        {data.excluded_jobs > 0 && (
          <span className="text-amber-400/60">
            ({data.excluded_jobs} excluded)
          </span>
        )}
      </div>
    </Tooltip>
  );
}
