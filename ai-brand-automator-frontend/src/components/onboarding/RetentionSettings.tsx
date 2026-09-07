'use client';

/**
 * Retention window configuration (M-03, AC-3).
 *
 * The backlog is explicit about what this component prevents: "we lost eight
 * months of onboarding data by changing a dropdown." When the new value is
 * shorter than the current one, the backend's PATCH returns an `impact` block
 * counting subjects and sessions that will be deleted at the next enforcement
 * run. This component shows that count and asks for confirmation before saving.
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Clock, Loader2, ShieldCheck } from 'lucide-react';

import {
  getRetentionConfig,
  updateRetentionConfig,
  type RetentionConfig,
  type RetentionUpdateResponse,
} from '@/lib/onboarding-sessions';
import { useTenantRole } from '@/hooks/useTenantRole';

export default function RetentionSettings() {
  const { isAdmin } = useTenantRole();
  const [config, setConfig] = useState<RetentionConfig | null>(null);
  const [inputDays, setInputDays] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingResult, setPendingResult] = useState<RetentionUpdateResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRetentionConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setInputDays(String(data.retention_days));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load retention config');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = useCallback(async () => {
    const days = Number(inputDays);
    if (!Number.isInteger(days) || days < 1 || days > 3650) {
      setError('Retention must be between 1 and 3,650 days.');
      return;
    }

    setError(null);
    setSaving(true);
    try {
      const result = await updateRetentionConfig(days);
      if (result.impact && result.impact.subjects > 0) {
        setPendingResult(result);
        setSaving(false);
        return;
      }
      setConfig({
        retention_days: result.retention_days,
        is_default: result.is_default,
        next_enforcement_run: result.next_enforcement_run,
      });
      setPendingResult(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update retention');
    } finally {
      setSaving(false);
    }
  }, [inputDays]);

  const handleConfirm = useCallback(() => {
    if (!pendingResult) return;
    setConfig({
      retention_days: pendingResult.retention_days,
      is_default: pendingResult.is_default,
      next_enforcement_run: pendingResult.next_enforcement_run,
    });
    setInputDays(String(pendingResult.retention_days));
    setPendingResult(null);
  }, [pendingResult]);

  const handleCancel = useCallback(() => {
    setPendingResult(null);
    if (config) setInputDays(String(config.retention_days));
  }, [config]);

  if (loading) {
    return (
      <div className="glass-card flex items-center gap-2 p-6 text-brand-silver">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading retention settings…
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="glass-card p-6">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Clock className="h-4 w-4 text-brand-electric" aria-hidden />
          Data retention
        </h3>
        <p className="mt-2 text-sm text-brand-silver">
          Evidence is retained for{' '}
          <strong className="text-white">{config?.retention_days ?? 365} days</strong>.
          Only an Owner or Admin can change this.
        </p>
      </div>
    );
  }

  const currentDays = config?.retention_days ?? 365;
  const parsed = Number(inputDays);
  const isShortening =
    Number.isInteger(parsed) && parsed > 0 && parsed < currentDays;
  const isDirty = String(parsed) !== String(currentDays);

  return (
    <div className="glass-card space-y-4 p-6">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
        <Clock className="h-4 w-4 text-brand-electric" aria-hidden />
        Data retention
      </h3>

      <div>
        <label htmlFor="retention-days" className="block text-sm text-brand-silver">
          Keep onboarding evidence for
        </label>
        <div className="mt-1 flex items-center gap-2">
          <input
            id="retention-days"
            type="number"
            min={1}
            max={3650}
            value={inputDays}
            onChange={(e) => {
              setInputDays(e.target.value);
              setError(null);
              setPendingResult(null);
            }}
            className="w-24 rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
          />
          <span className="text-sm text-brand-silver">days</span>
        </div>
        {config?.is_default && (
          <p className="mt-1 text-xs text-brand-silver">
            Using platform default. Saving will create a tenant-specific override.
          </p>
        )}
      </div>

      {isShortening && !pendingResult && (
        <p className="flex items-start gap-2 rounded border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          Shortening retention may delete existing evidence. Save to see how many
          records would be affected.
        </p>
      )}

      {pendingResult?.impact && pendingResult.impact.subjects > 0 && (
        <div
          role="alert"
          className="space-y-2 rounded border border-rose-500/30 bg-rose-500/10 p-3"
        >
          <p className="flex items-start gap-2 text-sm text-rose-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
            This will delete evidence for{' '}
            <strong>{pendingResult.impact.subjects} subject(s)</strong> across{' '}
            <strong>{pendingResult.impact.sessions} session(s)</strong>.
          </p>
          <p className="text-xs text-rose-300/80">
            Deletion happens at the next enforcement run:{' '}
            {new Date(pendingResult.impact.enforced_at).toLocaleString()}.
            You can reverse this by increasing retention before then.
          </p>
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={handleConfirm}
              className="rounded bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500"
            >
              Confirm shorter retention
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded px-3 py-1.5 text-xs text-brand-silver hover:text-white"
            >
              Revert
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-rose-300">
          {error}
        </p>
      )}

      {!pendingResult && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !isDirty}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="mr-1.5 inline h-3 w-3 animate-spin" aria-hidden />
                Saving…
              </>
            ) : (
              'Save'
            )}
          </button>
          {config && !config.is_default && (
            <p className="text-xs text-brand-silver">
              Next enforcement:{' '}
              {new Date(config.next_enforcement_run).toLocaleString()}
            </p>
          )}
        </div>
      )}

      <p className="flex items-start gap-2 rounded border border-white/10 p-3 text-xs text-brand-silver">
        <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-electric" aria-hidden />
        Evidence older than the retention window is permanently deleted by a daily
        sweep. This includes recordings, transcripts, captured media, provenance
        records and any related golden-dataset candidates.
      </p>
    </div>
  );
}
