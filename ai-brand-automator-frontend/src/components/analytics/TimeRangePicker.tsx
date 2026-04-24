'use client';

import type { TimeRange } from '@/types/analytics';
import Tooltip from '@/components/ui/Tooltip';

interface TimeRangePickerProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

const ranges: { label: string; value: TimeRange }[] = [
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
  { label: '1y', value: '1y' },
];

export default function TimeRangePicker({ value, onChange }: TimeRangePickerProps) {
  return (
    <Tooltip text="Select the time window for analytics data. All KPIs, trends, and comparisons will be recalculated for the chosen period.">
      <div className="inline-flex rounded-lg border border-white/10 bg-white/5 p-1">
        {ranges.map((range) => (
          <button
            key={range.value}
            onClick={() => onChange(range.value)}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              value === range.value
                ? 'bg-brand-electric/20 text-brand-electric'
                : 'text-brand-silver hover:text-white hover:bg-white/5'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>
    </Tooltip>
  );
}
