'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { useTenantRole } from '@/hooks/useTenantRole';
import {
  approveWF2Request,
  fetchWF2Requests,
  rejectWF2Request,
  type WF2RerunRequest,
} from '@/lib/intelligence';

export default function WF2ApprovalQueue() {
  const { isAdmin } = useTenantRole();
  const [requests, setRequests] = useState<WF2RerunRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWF2Requests('pending');
      setRequests(data);
    } catch (e) {
      setRequests([]);
      setError(e instanceof Error ? e.message : 'Failed to load WF2 queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  if (!isAdmin) {
    return null;
  }

  async function approve(id: string) {
    setBusy(id);
    setError(null);
    try {
      await approveWF2Request(id);
      setRequests((prev) => prev.filter((r) => r.request_id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval failed');
    } finally {
      setBusy(null);
    }
  }

  async function reject(id: string) {
    setBusy(id);
    setError(null);
    try {
      await rejectWF2Request(id, reason);
      setRequests((prev) => prev.filter((r) => r.request_id !== id));
      setRejectingId(null);
      setReason('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Rejection failed');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-heading font-semibold text-white flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-amber-300" />
          WF2 Approval Queue
        </h2>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-xs text-brand-silver hover:text-white inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          Refresh
        </button>
      </div>

      {error && (
        <div className="glass-card p-3 rounded-lg border border-rose-500/40 text-sm text-rose-300">
          {error}
        </div>
      )}

      {loading && requests.length === 0 && (
        <div className="glass-card p-6 rounded-lg flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-brand-electric" />
        </div>
      )}

      {!loading && requests.length === 0 && !error && (
        <div className="glass-card p-6 rounded-lg text-sm text-brand-silver text-center">
          No pending WF2 approval requests.
        </div>
      )}

      {requests.map((r) => (
        <div
          key={r.request_id}
          className="glass-card p-4 rounded-lg border border-amber-500/20"
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono uppercase tracking-wide text-amber-300">
                  {r.requested_agent}
                </span>
                <span className="text-xs text-brand-silver">
                  expires {new Date(r.expires_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-white font-medium">{r.learning_headline}</p>
              <p className="mt-1 text-xs text-brand-silver">{r.rationale}</p>
            </div>
          </div>

          {rejectingId === r.request_id ? (
            <div className="mt-3 space-y-2">
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for rejection (optional)"
                className="w-full text-xs bg-black/30 border border-white/10 rounded p-2 text-white placeholder-brand-silver/50"
                rows={2}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy === r.request_id}
                  onClick={() => reject(r.request_id)}
                  className="text-xs px-3 py-1.5 rounded bg-rose-500/20 border border-rose-500/40 text-rose-200 hover:bg-rose-500/30 disabled:opacity-50"
                >
                  Confirm reject
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRejectingId(null);
                    setReason('');
                  }}
                  className="text-xs px-3 py-1.5 rounded border border-white/10 text-brand-silver hover:text-white"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                disabled={busy === r.request_id}
                onClick={() => approve(r.request_id)}
                className="btn-primary text-xs px-3 py-1.5 inline-flex items-center gap-1.5 disabled:opacity-50"
              >
                {busy === r.request_id ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                Approve & dispatch
              </button>
              <button
                type="button"
                disabled={busy === r.request_id}
                onClick={() => setRejectingId(r.request_id)}
                className="text-xs px-3 py-1.5 inline-flex items-center gap-1.5 rounded border border-white/10 text-brand-silver hover:text-white disabled:opacity-50"
              >
                <X className="h-3 w-3" />
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
