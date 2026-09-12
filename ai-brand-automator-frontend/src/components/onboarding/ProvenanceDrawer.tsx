'use client';

import { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';

import TranscriptView from '@/components/onboarding/TranscriptView';
import {
  getRecordingTranscript,
  type FieldProvenanceRow,
  type TranscriptSegment,
} from '@/lib/onboarding-sessions';

interface ProvenanceDrawerProps {
  row: FieldProvenanceRow | null;
  onClose: () => void;
}

export default function ProvenanceDrawer({
  row,
  onClose,
}: ProvenanceDrawerProps) {
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recordingId = row?.source_span?.recording_id ?? null;
  const initialTime = row?.source_span?.t_start ?? 0;

  useEffect(() => {
    if (!recordingId) return;
    let cancelled = false;
    const fetchTranscript = async () => {
      try {
        const segs = await getRecordingTranscript(recordingId);
        if (!cancelled) {
          setSegments(segs);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
          setSegments([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    setLoading(true);
    void fetchTranscript();
    return () => {
      cancelled = true;
    };
  }, [recordingId]);

  const handleSeek = useCallback(() => {
    // no-op: audio playback is out of scope for K-01
  }, []);

  useEffect(() => {
    if (!row) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [row, onClose]);

  if (!row) return null;

  const isTranscriptSource = row.source_span !== null;
  const isMediaSource =
    !isTranscriptSource && row.source_media !== null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-label="Source evidence">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative flex h-full w-full max-w-lg flex-col bg-brand-midnight shadow-xl">
        <div className="flex items-center justify-between border-b border-white/10 p-4">
          <h3 className="text-sm font-semibold text-white">
            Source evidence
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-brand-silver hover:bg-white/10 hover:text-white"
            aria-label="Close drawer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isTranscriptSource && (
            <>
              {loading && (
                <p className="text-sm text-brand-silver">
                  Loading transcript...
                </p>
              )}
              {error && (
                <p className="text-sm text-red-400">
                  Failed to load transcript.
                </p>
              )}
              {!loading && !error && segments.length > 0 && (
                <TranscriptView
                  segments={segments}
                  currentTime={initialTime}
                  onSeek={handleSeek}
                  initialTime={initialTime}
                />
              )}
              {!loading && !error && segments.length === 0 && (
                <p className="text-sm text-brand-silver">
                  No transcript segments found.
                </p>
              )}
            </>
          )}
          {isMediaSource && (
            <p className="text-sm text-brand-silver">
              Media source #{row.source_media}
            </p>
          )}
          {!isTranscriptSource && !isMediaSource && (
            <p className="text-sm text-brand-silver">
              No source evidence available.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
