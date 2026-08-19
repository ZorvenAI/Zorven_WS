'use client';

/**
 * CaptureControl — photo capture with usage tagging (H-01, §11).
 *
 * State machine: idle → preview → confirm → tagging → idle.
 *
 * §11's focus rule does not apply here: CaptureControl is operator-initiated,
 * so the modal overlay is intentional, not agent-driven interruption.
 *
 * Consent is checked identically to RecorderControl (F-01, IG-08): the camera
 * cannot open without an active ConsentRecord.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, X, RotateCcw, Upload } from 'lucide-react';

import type { UsageTag } from '@/lib/onboarding-sessions';

type Phase = 'idle' | 'preview' | 'confirm' | 'tagging';

export const USAGE_TAGS: { value: UsageTag; label: string }[] = [
  { value: 'business_photo', label: 'Business photo' },
  { value: 'previous_ad', label: 'Previous ad' },
  { value: 'brand_asset', label: 'Brand asset' },
  { value: 'identity_document', label: 'Identity document' },
  { value: 'other', label: 'Other' },
];

export interface CaptureControlProps {
  consentGranted: boolean;
  onRecordConsent?: () => void;
  onCapture?: (blob: Blob, tag: UsageTag) => void;
}

export default function CaptureControl({
  consentGranted,
  onRecordConsent,
  onCapture,
}: CaptureControlProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [selectedTag, setSelectedTag] = useState<UsageTag | null>(null);
  const [snapshot, setSnapshot] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const dismiss = useCallback(() => {
    stopCamera();
    setPhase('idle');
    setSnapshot(null);
    setSelectedTag(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
  }, [stopCamera, previewUrl]);

  useEffect(() => {
    return () => {
      stopCamera();
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [stopCamera, previewUrl]);

  const openCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      setPhase('preview');
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      });
    } catch {
      // Camera not available or denied — stay idle.
    }
  }, []);

  const takePhoto = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        stopCamera();
        setSnapshot(blob);
        setPreviewUrl(URL.createObjectURL(blob));
        setPhase('confirm');
      },
      'image/jpeg',
      0.95,
    );
  }, [stopCamera]);

  const retake = useCallback(() => {
    setSnapshot(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setSelectedTag(null);
    void openCamera();
  }, [openCamera, previewUrl]);

  const confirmPhoto = useCallback(() => {
    setPhase('tagging');
  }, []);

  const submitCapture = useCallback(() => {
    if (!snapshot || !selectedTag || !onCapture) return;
    onCapture(snapshot, selectedTag);
    dismiss();
  }, [snapshot, selectedTag, onCapture, dismiss]);

  if (!consentGranted) {
    return (
      <button
        type="button"
        aria-disabled="true"
        onClick={onRecordConsent}
        className="flex w-full items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm text-brand-silver"
      >
        <Camera aria-hidden="true" className="h-4 w-4 shrink-0" />
        Capture photo
      </button>
    );
  }

  if (phase === 'idle') {
    return (
      <button
        type="button"
        onClick={openCamera}
        className="flex w-full items-center gap-2 rounded border border-white/15 px-3 py-2 text-sm text-white hover:bg-white/5"
      >
        <Camera aria-hidden="true" className="h-4 w-4 shrink-0" />
        Capture photo
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="Photo capture"
      data-testid="capture-overlay"
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

        {phase === 'preview' && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-white">Camera preview</h3>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              data-testid="camera-preview"
              className="w-full rounded bg-black"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={dismiss}
                className="flex-1 rounded border border-white/15 px-3 py-2 text-sm text-brand-silver"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={takePhoto}
                className="btn-primary flex-1 rounded px-3 py-2 text-sm"
              >
                Take photo
              </button>
            </div>
          </div>
        )}

        {phase === 'confirm' && previewUrl && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-white">Review photo</h3>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Captured photo"
              data-testid="capture-preview"
              className="w-full rounded"
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
                onClick={confirmPhoto}
                className="btn-primary flex-1 rounded px-3 py-2 text-sm"
              >
                Use this photo
              </button>
            </div>
          </div>
        )}

        {phase === 'tagging' && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-white">
              What is this photo?
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
      </div>
    </div>
  );
}
