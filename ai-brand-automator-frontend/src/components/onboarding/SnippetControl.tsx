'use client';

/**
 * SnippetControl -- short video snippet capture with usage tagging (H-02, SS11).
 *
 * State machine: idle -> recording -> confirm -> tagging -> idle.
 *
 * Parallel to CaptureControl (H-01) but uses MediaRecorder for video rather
 * than canvas snapshot for photos. The tagging phase is identical -- same five
 * usage tags, same radio picker, same onCapture(blob, tag) signature.
 *
 * AC-3: the hook acquires video-only (audio: false). The meeting's audio
 * recording continues without interruption.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Video, X, RotateCcw, Upload } from 'lucide-react';

import { USAGE_TAGS } from '@/components/onboarding/CaptureControl';
import {
  useSnippetRecorder,
  SNIPPET_MAX_SECONDS,
} from '@/hooks/useSnippetRecorder';
import type { UsageTag } from '@/lib/onboarding-sessions';

type Phase = 'idle' | 'recording' | 'confirm' | 'tagging';

export interface SnippetControlProps {
  consentGranted: boolean;
  onRecordConsent?: () => void;
  onCapture?: (blob: Blob, tag: UsageTag) => void;
}

export default function SnippetControl({
  consentGranted,
  onRecordConsent,
  onCapture,
}: SnippetControlProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [selectedTag, setSelectedTag] = useState<UsageTag | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const playbackRef = useRef<HTMLVideoElement>(null);

  const snippet = useSnippetRecorder();

  const dismiss = useCallback(() => {
    snippet.reset();
    setPhase('idle');
    setSelectedTag(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
  }, [snippet, previewUrl]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    if (snippet.state === 'recording' && snippet.stream && videoRef.current) {
      videoRef.current.srcObject = snippet.stream;
    }
  }, [snippet.state, snippet.stream]);

  useEffect(() => {
    if (snippet.state === 'stopped' && snippet.videoBlob && phase === 'recording') {
      const url = URL.createObjectURL(snippet.videoBlob);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(url);
      setPhase('confirm');
    }
  }, [snippet.state, snippet.videoBlob, phase, previewUrl]);

  const startRecording = useCallback(async () => {
    setSelectedTag(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    await snippet.start();
    setPhase('recording');
  }, [snippet, previewUrl]);

  const stopRecording = useCallback(() => {
    snippet.stop();
  }, [snippet]);

  const retake = useCallback(() => {
    snippet.reset();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setSelectedTag(null);
    void startRecording();
  }, [snippet, previewUrl, startRecording]);

  const confirmVideo = useCallback(() => {
    setPhase('tagging');
  }, []);

  const submitCapture = useCallback(() => {
    if (!snippet.videoBlob || !selectedTag || !onCapture) return;
    onCapture(snippet.videoBlob, selectedTag);
    dismiss();
  }, [snippet.videoBlob, selectedTag, onCapture, dismiss]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (!consentGranted) {
    return (
      <button
        type="button"
        aria-disabled="true"
        onClick={onRecordConsent}
        className="flex w-full items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm text-brand-silver"
      >
        <Video aria-hidden="true" className="h-4 w-4 shrink-0" />
        Capture video
      </button>
    );
  }

  if (phase === 'idle') {
    return (
      <button
        type="button"
        onClick={startRecording}
        className="flex w-full items-center gap-2 rounded border border-white/15 px-3 py-2 text-sm text-white hover:bg-white/5"
      >
        <Video aria-hidden="true" className="h-4 w-4 shrink-0" />
        Capture video
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="Video capture"
      data-testid="snippet-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
    >
      <div className="glass-card relative w-full max-w-md p-6">
        <button
          type="button"
          onClick={dismiss}
          aria-label="Close"
          className="absolute right-3 top-3 text-brand-silver hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>

        {phase === 'recording' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Recording</h3>
              <span className="text-sm tabular-nums text-brand-silver">
                {formatTime(snippet.elapsedSeconds)} / {formatTime(SNIPPET_MAX_SECONDS)}
              </span>
            </div>

            <div className="relative">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                data-testid="snippet-preview"
                className="w-full rounded bg-black"
              />
              {snippet.secondsRemaining !== null && (
                <div
                  data-testid="countdown-overlay"
                  className="absolute inset-0 flex items-center justify-center"
                >
                  <span className="rounded-full bg-black/60 px-4 py-2 text-2xl font-bold tabular-nums text-white">
                    {snippet.secondsRemaining}
                  </span>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={stopRecording}
              className="btn-primary w-full rounded px-3 py-2 text-sm"
            >
              Stop recording
            </button>
          </div>
        )}

        {phase === 'confirm' && previewUrl && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-white">Review video</h3>
            <video
              ref={playbackRef}
              src={previewUrl}
              controls
              playsInline
              data-testid="snippet-playback"
              className="w-full rounded bg-black"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={retake}
                className="flex flex-1 items-center justify-center gap-1 rounded border border-white/15 px-3 py-2 text-sm text-brand-silver"
              >
                <RotateCcw className="h-3 w-3" aria-hidden />
                Retake
              </button>
              <button
                type="button"
                onClick={confirmVideo}
                className="btn-primary flex-1 rounded px-3 py-2 text-sm"
              >
                Use this video
              </button>
            </div>
          </div>
        )}

        {phase === 'tagging' && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-white">
              What is this video?
            </h3>
            <fieldset>
              <legend className="sr-only">Usage tag</legend>
              <div className="space-y-2" data-testid="tag-picker">
                {USAGE_TAGS.map(({ value, label }) => (
                  <label
                    key={value}
                    className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm transition-colors ${
                      selectedTag === value
                        ? 'border-brand-electric bg-brand-electric/10 text-white'
                        : 'border-white/10 text-brand-silver hover:border-white/20'
                    }`}
                  >
                    <input
                      type="radio"
                      name="usage_tag"
                      value={value}
                      checked={selectedTag === value}
                      onChange={() => setSelectedTag(value)}
                      className="sr-only"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <button
              type="button"
              disabled={selectedTag === null}
              onClick={submitCapture}
              data-testid="upload-btn"
              className="btn-primary flex w-full items-center justify-center gap-2 rounded px-3 py-2 text-sm disabled:opacity-50"
            >
              <Upload className="h-4 w-4" aria-hidden />
              Upload
            </button>
          </div>
        )}

        {snippet.error && (
          <p className="mt-3 text-sm text-red-400">{snippet.error}</p>
        )}
      </div>
    </div>
  );
}
