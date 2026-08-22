'use client';

/**
 * RecordingsLibrary — the real recording + capture list for the right rail (I-01).
 *
 * Replaces the placeholder `recordingCount` text from E-02. Each recording
 * shows status, duration, and play/delete actions. Captures show type icon,
 * filename, and usage_tag badge (same as E-02 but now from the polling hook).
 *
 * Design §11 interaction rule: nothing steals focus. New items appear at the
 * top (newest first) but do not auto-scroll.
 */

import { useCallback, useRef, useState } from 'react';
import { AlertTriangle, Camera, Check, FileText, Mic, Play, Square, Trash2, Video } from 'lucide-react';

import {
  deleteRecording,
  getRecordingPlaybackUrl,
  type CapturedMedia,
  type RecordingItem,
} from '@/lib/onboarding-sessions';

// ── Status rendering ──

const STATUS_LABELS: Record<string, string> = {
  RECORDING: 'Recording',
  UPLOADED: 'Processing',
  TRANSCRIBED: 'Transcribed',
  SUMMARIZED: 'Ready',
  FAILED: 'Failed',
};

function StatusChip({ status }: { status: string }) {
  switch (status) {
    case 'RECORDING':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" />
          {STATUS_LABELS[status]}
        </span>
      );
    case 'UPLOADED':
      return (
        <span className="text-xs text-yellow-400">
          {STATUS_LABELS[status]}
        </span>
      );
    case 'TRANSCRIBED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400">
          <Check className="h-3 w-3" aria-hidden />
          {STATUS_LABELS[status]}
        </span>
      );
    case 'SUMMARIZED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400">
          <FileText className="h-3 w-3" aria-hidden />
          {STATUS_LABELS[status]}
        </span>
      );
    case 'FAILED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-400">
          <AlertTriangle className="h-3 w-3" aria-hidden />
          {STATUS_LABELS[status]}
        </span>
      );
    default:
      return <span className="text-xs text-brand-silver">{status}</span>;
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ── Props ──

export interface RecordingsLibraryProps {
  recordings: RecordingItem[];
  captures: CapturedMedia[];
  canDelete: boolean;
  onDeleted?: () => void;
}

// ── Component ──

export default function RecordingsLibrary({
  recordings,
  captures,
  canDelete,
  onDeleted,
}: RecordingsLibraryProps) {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [loadingPlay, setLoadingPlay] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const handlePlay = useCallback(async (recordingId: string) => {
    if (playingId === recordingId) {
      audioRef.current?.pause();
      setPlayingId(null);
      setPlaybackUrl(null);
      return;
    }
    setLoadingPlay(true);
    try {
      const url = await getRecordingPlaybackUrl(recordingId);
      if (url) {
        setPlaybackUrl(url);
        setPlayingId(recordingId);
      }
    } catch {
      // Silent — the button stays available for retry.
    } finally {
      setLoadingPlay(false);
    }
  }, [playingId]);

  const handleDelete = useCallback(async (recordingId: string) => {
    try {
      await deleteRecording(recordingId);
      if (playingId === recordingId) {
        setPlayingId(null);
        setPlaybackUrl(null);
      }
      onDeleted?.();
    } catch {
      // Silent — the button stays available for retry.
    }
  }, [playingId, onDeleted]);

  const hasItems = recordings.length > 0 || captures.length > 0;

  if (!hasItems) {
    return (
      <p className="text-sm text-brand-silver">
        Recordings and captured media appear here during the meeting.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {recordings.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
            Recordings
          </h3>
          <ul className="space-y-1.5" data-testid="recordings-list">
            {recordings.map((r) => {
              const canPlay =
                r.status !== 'RECORDING' && r.audio_asset != null;
              const isPlaying = playingId === r.id;

              return (
                <li
                  key={r.id}
                  className="rounded border border-white/10 px-3 py-2"
                >
                  <div className="flex items-center gap-2 text-sm">
                    <Mic
                      aria-hidden
                      className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                    />
                    <span className="text-white">
                      {formatDuration(r.duration_s)}
                    </span>
                    <StatusChip status={r.status} />

                    <span className="flex-1" />

                    {canPlay && (
                      <button
                        type="button"
                        aria-label={isPlaying ? 'Stop playback' : 'Play recording'}
                        disabled={loadingPlay}
                        onClick={() => void handlePlay(r.id)}
                        className="rounded p-1 text-brand-silver hover:text-white disabled:opacity-50"
                      >
                        {isPlaying ? (
                          <Square className="h-3.5 w-3.5" />
                        ) : (
                          <Play className="h-3.5 w-3.5" />
                        )}
                      </button>
                    )}

                    {canDelete && (
                      <button
                        type="button"
                        aria-label="Delete recording"
                        onClick={() => void handleDelete(r.id)}
                        className="rounded p-1 text-brand-silver hover:text-red-400"
                        data-testid="delete-recording"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>

                  {isPlaying && playbackUrl && (
                    <audio
                      ref={audioRef}
                      src={playbackUrl}
                      controls
                      autoPlay
                      className="mt-2 w-full"
                      onEnded={() => {
                        setPlayingId(null);
                        setPlaybackUrl(null);
                      }}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {captures.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
            Captures
          </h3>
          <ul className="space-y-1.5" data-testid="captures-list">
            {captures.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm"
              >
                {c.file_type === 'video' ? (
                  <Video
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                  />
                ) : (
                  <Camera
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                  />
                )}
                <span className="truncate text-white">{c.file_name}</span>
                <span className="shrink-0 rounded bg-brand-electric/20 px-1.5 py-0.5 text-xs text-brand-electric">
                  {c.usage_tag.replace(/_/g, ' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
