'use client';

import { useState } from 'react';
import { Check, FileText, Image, Loader2, X } from 'lucide-react';
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
  onConfirm?: (row: FieldProvenanceRow) => Promise<void>;
  onEdit?: (row: FieldProvenanceRow, finalValue: unknown) => Promise<void>;
}

export default function ProvenanceCard({
  row,
  onViewSource,
  onConfirm,
  onEdit,
}: ProvenanceCardProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);

  const hasSource = row.source_span !== null || row.source_media !== null;
  const confidencePct =
    row.confidence != null ? Math.round(Number(row.confidence) * 100) : null;

  const handleConfirm = async () => {
    if (!onConfirm) return;
    setSaving(true);
    try {
      await onConfirm(row);
    } finally {
      setSaving(false);
    }
  };

  const startEdit = () => {
    setEditValue(displayValue(row.extracted_value));
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setEditValue('');
  };

  const saveEdit = async () => {
    if (!onEdit) return;
    setSaving(true);
    try {
      await onEdit(row, editValue);
      setEditing(false);
      setEditValue('');
    } finally {
      setSaving(false);
    }
  };

  const canConfirm =
    onConfirm && (row.status === 'PENDING' || row.status === 'CONFLICT');
  const canEdit =
    onEdit &&
    (row.status === 'PENDING' ||
      row.status === 'CONFIRMED' ||
      row.status === 'CONFLICT');

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

      {editing && (
        <div className="mb-3 space-y-2">
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full rounded border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-brand-silver focus:border-brand-electric focus:outline-none"
            rows={3}
            aria-label={`Edit value for ${humanFieldName(row.field_name)}`}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={saveEdit}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded bg-purple-500/20 px-3 py-1 text-xs text-purple-400 hover:bg-purple-500/30 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              ) : (
                <Check className="h-3 w-3" aria-hidden />
              )}
              Save
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded px-3 py-1 text-xs text-brand-silver hover:bg-white/10 disabled:opacity-50"
            >
              <X className="h-3 w-3" aria-hidden />
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {confidencePct != null && (
          <div className="flex items-center gap-1.5 text-xs text-brand-silver">
            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-brand-electric"
                style={{ width: `${confidencePct}%` }}
              />
            </div>
            <span>{confidencePct}%</span>
          </div>
        )}

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

        {canConfirm && !editing && (
          <button
            type="button"
            onClick={handleConfirm}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50"
          >
            {saving && (
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
            )}
            Confirm
          </button>
        )}

        {canEdit && !editing && (
          <button
            type="button"
            onClick={startEdit}
            className="rounded px-2 py-1 text-xs text-purple-400 hover:bg-purple-500/10"
          >
            Edit
          </button>
        )}
      </div>
    </div>
  );
}
