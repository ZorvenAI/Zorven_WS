'use client';

import { FileText, Image } from 'lucide-react';
import type {
  FieldProvenanceRow,
  FieldClassification,
  ProvenanceStatus,
} from '@/lib/onboarding-sessions';

const CLASSIFICATION_STYLE: Record<FieldClassification, string> = {
  KEY: 'bg-blue-500/20 text-blue-400',
  SECONDARY: 'bg-zinc-700/50 text-brand-silver',
};

const STATUS_STYLE: Record<ProvenanceStatus, string> = {
  PENDING: 'bg-yellow-500/20 text-yellow-400',
  CONFIRMED: 'bg-emerald-500/20 text-emerald-400',
  EDITED: 'bg-purple-500/20 text-purple-400',
  CONFLICT: 'bg-red-500/20 text-red-400',
};

function humanFieldName(raw: string): string {
  return raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

interface ProvenanceCardProps {
  row: FieldProvenanceRow;
  onViewSource?: (row: FieldProvenanceRow) => void;
  onConfirm?: (row: FieldProvenanceRow) => void;
  onEdit?: (row: FieldProvenanceRow) => void;
}

export default function ProvenanceCard({
  row,
  onViewSource,
  onConfirm,
  onEdit,
}: ProvenanceCardProps) {
  const hasSource = row.source_span !== null || row.source_media !== null;
  const confidencePct = Math.round(row.confidence * 100);

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-medium text-white">
          {humanFieldName(row.field_name)}
        </h4>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${CLASSIFICATION_STYLE[row.classification]}`}
        >
          {row.classification}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLE[row.status]}`}
        >
          {row.status}
        </span>
      </div>

      <p className="mb-3 whitespace-pre-wrap text-sm text-brand-silver">
        {displayValue(row.extracted_value)}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-brand-silver">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-brand-electric"
              style={{ width: `${confidencePct}%` }}
            />
          </div>
          <span>{confidencePct}%</span>
        </div>

        {hasSource && onViewSource && (
          <button
            type="button"
            onClick={() => onViewSource(row)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-brand-electric hover:bg-white/10"
            aria-label={`View source for ${humanFieldName(row.field_name)}`}
          >
            {row.source_span ? (
              <FileText className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <Image className="h-3.5 w-3.5" aria-hidden />
            )}
            View source
          </button>
        )}

        {onConfirm && row.status === 'PENDING' && (
          <button
            type="button"
            onClick={() => onConfirm(row)}
            className="rounded px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-500/10"
          >
            Confirm
          </button>
        )}

        {onEdit && (row.status === 'PENDING' || row.status === 'CONFIRMED') && (
          <button
            type="button"
            onClick={() => onEdit(row)}
            className="rounded px-2 py-1 text-xs text-purple-400 hover:bg-purple-500/10"
          >
            Edit
          </button>
        )}
      </div>
    </div>
  );
}
