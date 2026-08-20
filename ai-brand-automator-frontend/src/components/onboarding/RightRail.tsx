'use client';

/**
 * The meeting view's right rail (E-02, Design §11).
 *
 * RecorderControl, CaptureControl (H-01) and RecordingsLibrary (I-01) live
 * here. The rail scrolls independently so a long media list cannot push the
 * capture controls off screen (FR-LIVE-02).
 */

import { Camera, Video } from 'lucide-react';

import RecorderControl from '@/components/onboarding/RecorderControl';
import CaptureControl from '@/components/onboarding/CaptureControl';
import SnippetControl from '@/components/onboarding/SnippetControl';
import type { CapturedMedia, UsageTag } from '@/lib/onboarding-sessions';

export interface RightRailProps {
  /** Placeholder count until I-01 lists real recordings. */
  recordingCount?: number;
  /** Whether an active ConsentRecord exists for this session (F-01). */
  consentGranted?: boolean;
  /** F-03: passed to the recorder so it can open a MeetingRecording. */
  sessionId?: string | null;
  /** Opens the consent modal. AC-1: the disabled control still does this. */
  onRecordConsent?: () => void;
  /** H-01: called when a photo is captured and tagged. */
  onCapture?: (blob: Blob, tag: UsageTag) => void;
  /** H-01: completed captures to display in the scroller. */
  captures?: CapturedMedia[];
}

export default function RightRail({
  recordingCount = 0,
  consentGranted = false,
  sessionId,
  onRecordConsent,
  onCapture,
  captures = [],
}: RightRailProps) {
  const itemCount = recordingCount + captures.length;

  return (
    <aside
      aria-labelledby="rail-heading"
      className="glass-card flex min-h-0 flex-col p-5"
    >
      <h2 id="rail-heading" className="text-sm font-semibold text-white">
        Recordings and captures
      </h2>

      <div className="mt-3 space-y-2">
        <RecorderControl
          consentGranted={consentGranted}
          sessionId={sessionId}
          onRecordConsent={onRecordConsent}
        />

        <CaptureControl
          consentGranted={consentGranted}
          onRecordConsent={onRecordConsent}
          onCapture={onCapture}
        />

        <SnippetControl
          consentGranted={consentGranted}
          onRecordConsent={onRecordConsent}
          onCapture={onCapture}
        />
      </div>

      <div
        data-testid="rail-scroller"
        className="mt-4 min-h-0 flex-1 overflow-y-auto"
      >
        {captures.length > 0 && (
          <ul className="space-y-2" data-testid="captured-media-list">
            {captures.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm"
              >
                {c.file_type === 'video' ? (
                  <Video aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-brand-silver" />
                ) : (
                  <Camera aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-brand-silver" />
                )}
                <span className="truncate text-white">{c.file_name}</span>
                <span className="shrink-0 rounded bg-brand-electric/20 px-1.5 py-0.5 text-xs text-brand-electric">
                  {c.usage_tag.replace(/_/g, ' ')}
                </span>
              </li>
            ))}
          </ul>
        )}

        {itemCount === 0 && (
          <p className="text-sm text-brand-silver">
            Recordings and captured media appear here during the meeting.
          </p>
        )}

        {recordingCount > 0 && (
          <p className="text-sm text-brand-silver">
            {recordingCount} recording{recordingCount === 1 ? '' : 's'}
          </p>
        )}
      </div>
    </aside>
  );
}
