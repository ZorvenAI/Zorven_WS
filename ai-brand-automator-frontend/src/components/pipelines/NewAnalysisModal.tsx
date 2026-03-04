/**
 * NewAnalysisModal — form for creating a new analysis job.
 *
 * Fetches available manifests and lets the user pick one
 * (or leave blank for auto-detect), enter a prompt, and submit.
 */

'use client';

import { useEffect, useState } from 'react';
import { X, Play, Loader2 } from 'lucide-react';
import { listManifests, createJob } from '@/lib/orchestration';
import type { PipelineManifestListItem } from '@/types/orchestration';

interface NewAnalysisModalProps {
  open: boolean;
  onClose: () => void;
  /** Called with the new job_id after successful creation. */
  onCreated: (jobId: string) => void;
}

export default function NewAnalysisModal({
  open,
  onClose,
  onCreated,
}: NewAnalysisModalProps) {
  const [manifests, setManifests] = useState<PipelineManifestListItem[]>([]);
  const [selectedManifest, setSelectedManifest] = useState<number | ''>('');
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch manifests on open
  useEffect(() => {
    if (!open) return;
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
  }, [open]);

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setSelectedManifest('');
      setPrompt('');
      setError(null);
    }
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError('Please enter a prompt.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const job = await createJob({
        manifest: selectedManifest === '' ? null : selectedManifest,
        input_prompt: prompt.trim(),
      });
      onCreated(job.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-lg mx-4 glass-card p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-heading text-lg font-heading font-bold text-white">
            New Analysis
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-brand-silver/60 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

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
              Prompt
            </label>
            <textarea
              id="prompt"
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe what you want the pipeline to analyse…"
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-brand-silver placeholder:text-brand-silver/30 focus:outline-none focus:ring-2 focus:ring-brand-electric/50 resize-none"
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="btn-outline px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary flex items-center gap-2 px-4 py-2 text-sm disabled:opacity-60"
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
    </div>
  );
}
