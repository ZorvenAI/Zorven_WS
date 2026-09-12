import type { FieldProvenanceRow } from '@/lib/onboarding-sessions';

interface ProvenanceBadgeProps {
  row: FieldProvenanceRow | undefined;
}

export default function ProvenanceBadge({ row }: ProvenanceBadgeProps) {
  if (!row) return null;

  const confidence = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '';
  const title = confidence
    ? `AI-extracted (${confidence} confidence)`
    : 'AI-extracted';

  return (
    <span
      className="ml-2 inline-flex items-center rounded bg-brand-electric/15 px-1.5 py-0.5 text-[10px] font-medium text-brand-electric"
      title={title}
    >
      AI
    </span>
  );
}
