'use client';

import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2, RefreshCw } from 'lucide-react';

import { apiClient } from '@/lib/api';

interface DescriptionData {
  description: string;
  has_clean_transcript: boolean;
}

export interface DescriptionTabProps {
  sessionId: string;
}

export default function DescriptionTab({ sessionId }: DescriptionTabProps) {
  const [description, setDescription] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDescription = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get(
        `/onboarding/sessions/${sessionId}/description/`,
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as DescriptionData;
      setDescription(data.description || '');
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to load description';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchDescription();
  }, [fetchDescription]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-brand-silver" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-brand-silver">
        <p className="text-sm">{error}</p>
        <button
          type="button"
          onClick={fetchDescription}
          className="inline-flex items-center gap-1.5 text-sm text-brand-electric hover:underline"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </button>
      </div>
    );
  }

  if (!description) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-brand-silver">
        <FileText className="h-10 w-10 opacity-30" />
        <p className="text-sm">
          No description available yet. It will be generated after the meeting
          is processed.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">
          Brand-Building Description
        </h2>
        <button
          type="button"
          onClick={fetchDescription}
          className="inline-flex items-center gap-1.5 rounded border border-white/10 px-2.5 py-1 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>
      <article className="glass-card prose prose-invert max-w-none p-6 text-sm leading-relaxed text-brand-silver">
        {description.split('\n').map((line, i) => {
          if (line.startsWith('## ')) {
            return (
              <h3
                key={i}
                className="mb-2 mt-6 text-base font-semibold text-white first:mt-0"
              >
                {line.slice(3)}
              </h3>
            );
          }
          if (!line.trim()) return <br key={i} />;
          return (
            <p key={i} className="mb-1.5">
              {line}
            </p>
          );
        })}
      </article>
    </div>
  );
}
