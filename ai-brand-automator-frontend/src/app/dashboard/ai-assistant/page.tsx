/**
 * /dashboard/ai-assistant — Conversational AI pipeline launcher.
 *
 * Single-page workflow combining:
 * - Inline prompt input with pipeline manifest selector
 * - Active job tracking with ThoughtTrace
 * - Result display with ResultDashboard / BrandEquityDashboard
 *
 * Flow: enter prompt -> select pipeline -> run -> watch progress -> see results.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Play, Loader2, XCircle, RotateCcw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { usePollingJob } from '@/hooks/usePollingJob';
import { listManifests, createJob, cancelJob } from '@/lib/orchestration';
import type { PipelineManifestListItem } from '@/types/orchestration';
import ThoughtTrace from '@/components/pipelines/ThoughtTrace';
import ResultDashboard from '@/components/pipelines/ResultDashboard';

type Phase = 'input' | 'running' | 'completed' | 'failed';

export default function AiAssistantPage() {
  useAuth();

  // Form state
  const [manifests, setManifests] = useState<PipelineManifestListItem[]>([]);
  const [selectedManifest, setSelectedManifest] = useState<number | ''>('');
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Active job tracking
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const { job, quickStatus, error: pollError } = usePollingJob(activeJobId);

  // Derive the current phase
  const phase: Phase = (() => {
    if (!activeJobId) return 'input';
    if (!job) return 'running'; // still loading
    if (job.status === 'completed') return 'completed';
    if (job.status === 'failed') return 'failed';
    return 'running';
  })();

  // Fetch manifests on mount
  useEffect(() => {
    let cancelled = false;
    listManifests()
      .then((data) => {
        if (!cancelled) setManifests(data.filter((m) => m.is_active));
      })
      .catch(() => {
        if (!cancelled) setManifests([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setFormError('Please enter a prompt.');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    try {
      const newJob = await createJob({
        manifest: selectedManifest === '' ? null : selectedManifest,
        input_prompt: prompt.trim(),
      });
      setActiveJobId(newJob.job_id);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to start analysis');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = useCallback(async () => {
    if (!activeJobId) return;
    setCancelling(true);
    try {
      await cancelJob(activeJobId);
    } catch {
      // Best-effort
    } finally {
      setCancelling(false);
    }
  }, [activeJobId]);

  const handleReset = () => {
    setActiveJobId(null);
    setPrompt('');
    setSelectedManifest('');
    setFormError(null);
    setTimeout(() => promptRef.current?.focus(), 100);
  };

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />

      <div className="relative z-10 max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Back link */}
        <Link
          href="/dashboard"
          className="inline-flex items-center text-sm text-brand-silver/70 hover:text-brand-electric mb-6 transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to Dashboard
        </Link>

        {/* Header */}
        <div className="mb-8">
          <h1 className="font-heading text-2xl font-heading font-bold text-white">
            AI Assistant
          </h1>
          <p className="mt-1 text-sm text-brand-silver/60">
            Describe your analysis and let AI run the right pipeline
          </p>
        </div>

        {/* ── Input phase ── */}
        {phase === 'input' && (
          <div className="glass-card p-6">
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Pipeline selector */}
              <div>
                <label
                  htmlFor="manifest"
                  className="block text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-1.5"
                >
                  Pipeline
                </label>
                <select
                  id="manifest"
                  value={selectedManifest}
                  onChange={(e) =>
                    setSelectedManifest(
                      e.target.value === '' ? '' : Number(e.target.value),
                    )
                  }
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-brand-silver focus:outline-none focus:ring-2 focus:ring-brand-electric/50"
                >
                  <option value="">Auto-detect (let AI choose)</option>
                  {manifests.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} v{m.version}
                    </option>
                  ))}
                </select>
              </div>

              {/* Prompt */}
              <div>
                <label
                  htmlFor="prompt"
                  className="block text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-1.5"
                >
                  What would you like to analyse?
                </label>
                <textarea
                  ref={promptRef}
                  id="prompt"
                  rows={5}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="e.g. Perform an ISO 10668 brand valuation for Acme Corp using royalty relief methodology..."
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-brand-silver placeholder:text-brand-silver/30 focus:outline-none focus:ring-2 focus:ring-brand-electric/50 resize-none"
                />
              </div>

              {/* Error */}
              {formError && (
                <p className="text-sm text-red-400">{formError}</p>
              )}

              {/* Submit */}
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm disabled:opacity-60"
                >
                  {isSubmitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  Run Analysis
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── Running phase ── */}
        {phase === 'running' && job && (
          <div className="space-y-6">
            <div className="glass-card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-medium text-white">
                    {job.manifest_name ?? 'Auto-detect Pipeline'}
                  </p>
                  <p className="text-xs text-brand-silver/50 mt-1 truncate">
                    {job.input_prompt}
                  </p>
                </div>
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="btn-outline flex items-center gap-1.5 text-xs text-red-400 border-red-500/30 hover:bg-red-500/10 px-3 py-1.5"
                >
                  {cancelling ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  Cancel
                </button>
              </div>
              <ThoughtTrace
                progress={quickStatus?.progress ?? job.progress}
                jobStatus={job.status}
                lastThought={quickStatus?.last_thought}
                progressPercent={quickStatus?.progress_percent}
              />
            </div>
          </div>
        )}

        {/* Running but job not yet loaded */}
        {phase === 'running' && !job && (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 animate-spin text-brand-electric" />
          </div>
        )}

        {/* ── Completed phase ── */}
        {phase === 'completed' && job && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <p className="text-sm text-brand-silver/60">
                Analysis completed in{' '}
                {job.duration_seconds != null
                  ? `${job.duration_seconds.toFixed(1)}s`
                  : '—'}
              </p>
              <button
                onClick={handleReset}
                className="btn-outline flex items-center gap-1.5 text-sm px-3 py-2"
              >
                <RotateCcw className="w-4 h-4" />
                New Analysis
              </button>
            </div>

            {job.result_data && (
              <ResultDashboard
                resultData={job.result_data}
                manifestName={job.manifest_name}
              />
            )}
          </div>
        )}

        {/* ── Failed phase ── */}
        {phase === 'failed' && job && (
          <div className="space-y-6">
            <div className="glass-card p-6 border-red-500/30">
              <h3 className="font-heading text-sm font-heading font-semibold text-red-400 mb-2">
                Analysis Failed
              </h3>
              <p className="text-sm text-brand-silver">
                {job.error_message || 'An unknown error occurred.'}
              </p>
            </div>
            <div className="flex justify-end">
              <button
                onClick={handleReset}
                className="btn-outline flex items-center gap-1.5 text-sm px-3 py-2"
              >
                <RotateCcw className="w-4 h-4" />
                Try Again
              </button>
            </div>
          </div>
        )}

        {/* Poll error (non-fatal) */}
        {pollError && phase === 'running' && (
          <div className="glass-card p-4 border-amber-500/30 mt-4">
            <p className="text-xs text-amber-400">{pollError}</p>
          </div>
        )}
      </div>
    </div>
  );
}
