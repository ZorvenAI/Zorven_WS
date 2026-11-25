'use client';

import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2, RefreshCw } from 'lucide-react';

import { apiClient } from '@/lib/api';

interface MeetingDescription {
  recording_id: number;
  started_at: string | null;
  description: string;
  transcript_clean: string;
}

interface DescriptionData {
  meetings: MeetingDescription[];
}

type SubTab = 'description' | 'transcript';

export interface DescriptionTabProps {
  sessionId: string;
}

export default function DescriptionTab({ sessionId }: DescriptionTabProps) {
  const [meetings, setMeetings] = useState<MeetingDescription[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('description');
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
      const loaded = (data.meetings ?? []).filter(
        (m) => m.description || m.transcript_clean,
      );
      setMeetings(loaded);
      setSelectedIndex(Math.max(loaded.length - 1, 0));
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

  const selected = meetings[selectedIndex];
  const description = selected?.description ?? '';
  const transcriptClean = selected?.transcript_clean ?? '';

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

  if (!description && !transcriptClean) {
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

  const renderMarkdown = (text: string) =>
    text.split('\n').map((line, i) => {
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
      if (line.trim() === '---') {
        return <hr key={i} className="my-4 border-white/10" />;
      }
      if (!line.trim()) return <br key={i} />;

      const isBullet = /^\s*[*-]\s/.test(line);
      const raw = isBullet ? line.replace(/^\s*[*-]\s+/, '') : line;
      const parts = raw.split(/(\*\*.+?\*\*)/g).map((p, j) =>
        p.startsWith('**') && p.endsWith('**') ? (
          <strong key={j} className="text-white">
            {p.slice(2, -2)}
          </strong>
        ) : (
          <span key={j}>{p}</span>
        ),
      );

      if (isBullet) {
        return (
          <div key={i} className="mb-1.5 flex gap-2 pl-2">
            <span className="mt-1 text-brand-electric">•</span>
            <span>{parts}</span>
          </div>
        );
      }
      return (
        <p key={i} className="mb-1.5">
          {parts}
        </p>
      );
    });

  return (
    <div className="p-6">
      {meetings.length > 1 && (
        <div
          className="mb-4 flex flex-wrap gap-2"
          role="tablist"
          aria-label="Meetings"
        >
          {meetings.map((m, i) => (
            <button
              key={m.recording_id}
              type="button"
              role="tab"
              aria-selected={i === selectedIndex}
              onClick={() => setSelectedIndex(i)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                i === selectedIndex
                  ? 'border-brand-electric bg-white/10 text-white'
                  : 'border-white/10 text-brand-silver hover:text-white'
              }`}
            >
              Meeting {i + 1}
              {m.started_at && (
                <span className="ml-1.5 opacity-70">
                  {new Date(m.started_at).toLocaleDateString()}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {description && transcriptClean ? (
            <div className="flex rounded-lg border border-white/10 p-0.5">
              <button
                type="button"
                onClick={() => setActiveSubTab('description')}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  activeSubTab === 'description'
                    ? 'bg-white/10 text-white'
                    : 'text-brand-silver hover:text-white'
                }`}
              >
                Description (T3)
              </button>
              <button
                type="button"
                onClick={() => setActiveSubTab('transcript')}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  activeSubTab === 'transcript'
                    ? 'bg-white/10 text-white'
                    : 'text-brand-silver hover:text-white'
                }`}
              >
                Clean Transcript (T2)
              </button>
            </div>
          ) : (
            <h2 className="text-lg font-semibold text-white">
              {description ? 'Brand-Building Description' : 'Clean Transcript'}
            </h2>
          )}
        </div>
        <button
          type="button"
          onClick={fetchDescription}
          className="inline-flex items-center gap-1.5 rounded border border-white/10 px-2.5 py-1 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>

      {(activeSubTab === 'description' && description) && (
        <article className="glass-card prose prose-invert max-w-none p-6 text-sm leading-relaxed text-brand-silver">
          {renderMarkdown(description)}
        </article>
      )}

      {(activeSubTab === 'transcript' || !description) && transcriptClean && (
        <article className="glass-card max-w-none p-6 text-sm leading-relaxed text-brand-silver">
          {typeof transcriptClean === 'string'
            ? transcriptClean.split('\n').map((line, i) => {
                if (!line.trim()) return <br key={i} />;
                const speakerMatch = line.match(/^(.+?):\s*(.*)/);
                if (speakerMatch) {
                  return (
                    <div key={i} className="mb-3">
                      <span className="font-medium text-brand-electric">
                        {speakerMatch[1]}:
                      </span>{' '}
                      <span>{speakerMatch[2]}</span>
                    </div>
                  );
                }
                return (
                  <p key={i} className="mb-1.5">
                    {line}
                  </p>
                );
              })
            : renderMarkdown(JSON.stringify(transcriptClean, null, 2))}
        </article>
      )}
    </div>
  );
}
