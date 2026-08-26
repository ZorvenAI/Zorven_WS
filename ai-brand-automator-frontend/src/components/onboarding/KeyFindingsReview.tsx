'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  CheckCircle,
  ChevronDown,
  FileWarning,
  Loader2,
  Send,
} from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import ProvenanceCard from '@/components/onboarding/ProvenanceCard';
import ProvenanceDrawer from '@/components/onboarding/ProvenanceDrawer';
import {
  confirmProvenance,
  editProvenance,
  getSessionDetail,
  getSessionProvenance,
  getRecordingDetail,
  listSessionRecordings,
  submitReview,
  type FieldProvenanceRow,
  type ProcessSummary,
  type ProvenanceGroup,
  type RecordingDetail,
  type SessionDetail,
} from '@/lib/onboarding-sessions';

const WORKFLOW_LABELS: Record<string, string> = {
  WF1: 'Discovery & Research',
  WF2: 'Brand Strategy',
  WF3: 'Campaign & Content',
};

const COVERAGE_CONSEQUENCES: Record<string, string> = {
  WF1: 'Market research and competitor analysis will have less input data to work from.',
  WF2: 'Brand positioning and identity outputs may be less precisely tailored.',
  WF3: 'Campaign architecture and creative generation will rely on broader assumptions.',
};

interface KeyFindingsReviewProps {
  sessionId: string;
}

export default function KeyFindingsReview({
  sessionId,
}: KeyFindingsReviewProps) {
  const router = useRouter();
  const { isAdmin, canEdit } = useTenantRole();

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [groups, setGroups] = useState<ProvenanceGroup[]>([]);
  const [recordings, setRecordings] = useState<RecordingDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerRow, setDrawerRow] = useState<FieldProvenanceRow | null>(null);
  const [secondaryOpen, setSecondaryOpen] = useState<Record<number, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sess, prov, recs] = await Promise.all([
        getSessionDetail(sessionId),
        getSessionProvenance(sessionId),
        listSessionRecordings(sessionId),
      ]);
      setSession(sess);
      setGroups(prov.groups);

      const details = await Promise.all(
        recs
          .filter((r) => r.has_summary)
          .map((r) => getRecordingDetail(r.id)),
      );
      setRecordings(details);
    } catch (err) {
      setError(String(err));
      setSession(null);
      setGroups([]);
      setRecordings([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary: ProcessSummary | null =
    session?.process_summary
      ? (session.process_summary as unknown as ProcessSummary)
      : null;

  const conflictRows = groups
    .flatMap((g) => g.fields)
    .filter((f) => f.status === 'CONFLICT');

  const coverageShortfalls = summary
    ? Object.entries(summary.coverage ?? {}).filter(([, v]) => v < 1.0)
    : [];

  const toggleSecondary = useCallback((page: number) => {
    setSecondaryOpen((prev) => ({ ...prev, [page]: !prev[page] }));
  }, []);

  const handleConfirm = useCallback(
    async (row: FieldProvenanceRow) => {
      await confirmProvenance(row.id);
      await load();
    },
    [load],
  );

  const handleEdit = useCallback(
    async (row: FieldProvenanceRow, finalValue: unknown) => {
      await editProvenance(row.id, finalValue);
      await load();
    },
    [load],
  );

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitReview(sessionId);
      router.push(`/onboarding/sessions/${sessionId}`);
    } catch (err) {
      setSubmitError(String(err));
    } finally {
      setSubmitting(false);
    }
  }, [sessionId, router]);

  const confirmCallbackForKey = isAdmin ? handleConfirm : undefined;
  const editCallbackForKey = isAdmin ? handleEdit : undefined;
  const confirmCallbackForSecondary = canEdit ? handleConfirm : undefined;
  const editCallbackForSecondary = canEdit ? handleEdit : undefined;

  const canSubmit =
    session?.legal_next_states?.includes('CONFIRMED') &&
    conflictRows.length === 0;

  const showSubmit = session?.legal_next_states?.includes('CONFIRMED');

  if (loading) {
    return (
      <div className="space-y-6">
        <p className="text-sm text-brand-silver">Loading review...</p>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="space-y-6">
        <p className="text-sm text-red-400">
          Failed to load review data.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href={`/onboarding/sessions/${sessionId}`}
          className="mb-3 inline-flex items-center gap-2 text-sm text-brand-silver hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to session
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-white">Key Findings</h1>
          <span className="rounded bg-blue-500/20 px-2 py-0.5 text-xs font-medium text-blue-400">
            {session.status.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Summary bar */}
      {summary && (
        <div className="glass-card grid grid-cols-2 gap-4 p-5 sm:grid-cols-4" data-testid="summary-bar">
          <div>
            <p className="text-xs text-brand-silver">Fields written</p>
            <p className="text-lg font-semibold text-white">
              {summary.fields_written}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-silver">Conflicts</p>
            <p className="text-lg font-semibold text-white">
              {summary.conflicts.length}
            </p>
          </div>
          <div title="Values considered but rejected because they lacked evidence">
            <p className="text-xs text-brand-silver">Dropped (ungrounded)</p>
            <p className="text-lg font-semibold text-white" data-testid="dropped-count">
              {summary.dropped_ungrounded}
            </p>
          </div>
          <div>
            <p className="text-xs text-brand-silver">Generated</p>
            <p className="text-sm font-medium text-white" data-testid="generated-list">
              {(summary.generated ?? []).length > 0
                ? (summary.generated ?? [])
                    .map((g) => g.replace(/_/g, ' '))
                    .join(', ')
                : 'None'}
            </p>
          </div>
        </div>
      )}

      {/* Conflicts — above field lists (K-01 AC-4) */}
      {conflictRows.length > 0 && (
        <section data-testid="conflicts-section" className="glass-card border border-amber-500/30 p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-400">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Unresolved conflicts ({conflictRows.length})
          </h2>
          <p className="mb-4 text-xs text-brand-silver">
            These fields have conflicting values from different sources and
            require manual resolution before final submission.
          </p>
          <div className="space-y-3">
            {conflictRows.map((row) => (
              <ProvenanceCard
                key={row.id}
                row={row}
                onViewSource={setDrawerRow}
                onConfirm={
                  row.classification === 'KEY'
                    ? confirmCallbackForKey
                    : confirmCallbackForSecondary
                }
                onEdit={
                  row.classification === 'KEY'
                    ? editCallbackForKey
                    : editCallbackForSecondary
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* Coverage shortfalls (K-01 AC-3) */}
      {coverageShortfalls.length > 0 && (
        <section data-testid="coverage-section" className="glass-card border border-yellow-500/30 p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-yellow-400">
            <FileWarning className="h-4 w-4" aria-hidden />
            Coverage shortfalls
          </h2>
          <ul className="mb-4 space-y-2">
            {coverageShortfalls.map(([wf, pct]) => (
              <li key={wf} className="text-sm text-brand-silver">
                <span className="font-medium text-white">
                  {WORKFLOW_LABELS[wf] ?? wf}
                </span>
                : {Math.round(pct * 100)}% covered.{' '}
                {COVERAGE_CONSEQUENCES[wf] ?? ''}
              </li>
            ))}
          </ul>
          <Link
            href="/onboarding"
            className="inline-flex items-center gap-2 rounded bg-yellow-500/10 px-3 py-1.5 text-sm text-yellow-400 hover:bg-yellow-500/20"
          >
            <Calendar className="h-4 w-4" aria-hidden />
            Schedule follow-up
          </Link>
        </section>
      )}

      {/* Recording summaries */}
      {recordings.length > 0 && (
        <section className="glass-card p-5">
          <h2 className="mb-3 text-sm font-semibold text-white">
            Recording summaries
          </h2>
          <div className="space-y-4">
            {recordings.map((rec) => (
              <div key={rec.id} className="rounded-lg bg-white/5 p-4">
                {rec.summary ? (
                  <>
                    <p className="mb-2 text-sm text-brand-silver">
                      {rec.summary.text}
                    </p>
                    {rec.summary.key_moments.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {rec.summary.key_moments.map((km, i) => (
                          <span
                            key={i}
                            className="rounded bg-brand-electric/10 px-2 py-0.5 text-xs text-brand-electric"
                          >
                            {km.label}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-brand-silver">
                    No summary available.
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Provenance groups — KEY prominent, SECONDARY collapsed */}
      {groups.map((group) => {
        const keyFields = group.fields.filter(
          (f) => f.classification === 'KEY' && f.status !== 'CONFLICT',
        );
        const secondaryFields = group.fields.filter(
          (f) => f.classification === 'SECONDARY' && f.status !== 'CONFLICT',
        );
        const pageKey = group.page ?? -1;
        const isOpen = secondaryOpen[pageKey] ?? false;

        if (keyFields.length === 0 && secondaryFields.length === 0) {
          return null;
        }

        return (
          <section key={pageKey} className="glass-card p-5">
            <h2 className="mb-4 text-sm font-semibold text-white">
              {group.label}
            </h2>

            {keyFields.length > 0 && (
              <div className="mb-4 space-y-3" data-testid="key-fields">
                {keyFields.map((row) => (
                  <ProvenanceCard
                    key={row.id}
                    row={row}
                    onViewSource={setDrawerRow}
                    onConfirm={confirmCallbackForKey}
                    onEdit={editCallbackForKey}
                  />
                ))}
              </div>
            )}

            {secondaryFields.length > 0 && (
              <div data-testid="secondary-fields">
                <button
                  type="button"
                  onClick={() => toggleSecondary(pageKey)}
                  className="mb-2 flex items-center gap-2 text-sm text-brand-silver hover:text-white"
                >
                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                    aria-hidden
                  />
                  <span>
                    Auto-filled fields ({secondaryFields.length})
                  </span>
                  <span className="rounded bg-zinc-700/50 px-1.5 py-0.5 text-xs">
                    review
                  </span>
                </button>
                {isOpen && (
                  <div className="space-y-3">
                    {secondaryFields.map((row) => (
                      <ProvenanceCard
                        key={row.id}
                        row={row}
                        onViewSource={setDrawerRow}
                        onConfirm={confirmCallbackForSecondary}
                        onEdit={editCallbackForSecondary}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        );
      })}

      {groups.length === 0 && !loading && (
        <div className="glass-card p-5 text-center">
          <p className="text-sm text-brand-silver">
            No provenance data available yet.
          </p>
        </div>
      )}

      {/* Submit review (AC-5) */}
      {showSubmit && (
        <div className="glass-card p-5" data-testid="submit-section">
          {session.status === 'CONFIRMED' && (
            <div className="flex items-center gap-2 text-sm text-emerald-400">
              <CheckCircle className="h-4 w-4" aria-hidden />
              Review submitted
            </div>
          )}
          {session.status !== 'CONFIRMED' && (
            <>
              {conflictRows.length > 0 && (
                <p className="mb-3 text-xs text-amber-400">
                  Resolve all {conflictRows.length} conflict(s) before
                  submitting.
                </p>
              )}
              {submitError && (
                <p className="mb-3 text-xs text-red-400">{submitError}</p>
              )}
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit || submitting}
                className="btn-primary inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="submit-button"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Send className="h-4 w-4" aria-hidden />
                )}
                Submit review
              </button>
            </>
          )}
        </div>
      )}

      {/* Provenance evidence drawer */}
      <ProvenanceDrawer row={drawerRow} onClose={() => setDrawerRow(null)} />
    </div>
  );
}
