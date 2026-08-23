'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Clock, FileText, Loader2, Pause, Play, X } from 'lucide-react';

import {
  getRecordingDetail,
  type RecordingDetail,
  type KeyMoment,
} from '@/lib/onboarding-sessions';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export interface RecordingPlayerProps {
  recordingId: string;
  onClose: () => void;
}

export default function RecordingPlayer({
  recordingId,
  onClose,
}: RecordingPlayerProps) {
  const [detail, setDetail] = useState<RecordingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getRecordingDetail(recordingId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [recordingId]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play();
    } else {
      audio.pause();
    }
  }, []);

  const seekTo = useCallback((t: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = t;
    void audio.play();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const audio = audioRef.current;
      if (!audio) return;
      if (e.key === ' ') {
        e.preventDefault();
        togglePlay();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        audio.currentTime = Math.max(0, audio.currentTime - 5);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 5);
      }
    },
    [togglePlay],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-brand-silver" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={onClose}
          className="flex items-center gap-1 text-sm text-brand-silver hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <p className="text-sm text-red-400">{error || 'Recording not found'}</p>
      </div>
    );
  }

  const summary = detail.summary;

  return (
    <div
      className="space-y-4"
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="region"
      aria-label="Recording player"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onClose}
          className="flex items-center gap-1 text-sm text-brand-silver hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Recording
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close player"
          className="rounded p-1 text-brand-silver hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Audio player */}
      {detail.playback_url && (
        <div className="rounded-lg border border-white/10 p-3">
          <audio
            ref={audioRef}
            src={detail.playback_url}
            preload="metadata"
            onTimeUpdate={() =>
              setCurrentTime(audioRef.current?.currentTime ?? 0)
            }
            onLoadedMetadata={() =>
              setDuration(audioRef.current?.duration ?? 0)
            }
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={togglePlay}
              aria-label={isPlaying ? 'Pause' : 'Play'}
              className="rounded-full bg-brand-electric p-2 text-white hover:bg-brand-electric/80"
            >
              {isPlaying ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
            </button>
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.1}
              value={currentTime}
              onChange={(e) => {
                const t = parseFloat(e.target.value);
                if (audioRef.current) audioRef.current.currentTime = t;
                setCurrentTime(t);
              }}
              className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-white/20 accent-brand-electric"
              aria-label="Seek"
            />
            <span className="shrink-0 text-xs tabular-nums text-brand-silver">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div className="space-y-3">
          <h3 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
            <FileText className="h-3.5 w-3.5" />
            Summary
          </h3>
          <div className="text-sm leading-relaxed text-white/90">
            {summary.text.split('\n\n').map((paragraph, i) => (
              <p key={i} className={i > 0 ? 'mt-2' : ''}>
                {paragraph}
              </p>
            ))}
          </div>

          {/* Key moments */}
          {summary.key_moments.length > 0 && (
            <div>
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
                <Clock className="h-3.5 w-3.5" />
                Key Moments
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {summary.key_moments.map((km: KeyMoment, i: number) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => seekTo(km.t)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-brand-electric/30 bg-brand-electric/10 px-2.5 py-1 text-xs text-brand-electric transition-colors hover:bg-brand-electric/20"
                  >
                    <span className="tabular-nums text-brand-electric/70">
                      {formatTime(km.t)}
                    </span>
                    {km.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!summary && !detail.playback_url && (
        <p className="text-sm text-brand-silver">
          No summary or playback available yet.
        </p>
      )}
    </div>
  );
}
