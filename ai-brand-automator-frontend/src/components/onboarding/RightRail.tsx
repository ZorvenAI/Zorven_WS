'use client';

/**
 * The meeting view's right rail (E-02, Design §11).
 *
 * RecorderControl, CaptureControl (H-01), SnippetControl (H-02) and
 * RecordingsLibrary (I-01) live here. The rail scrolls independently so a
 * long media list cannot push the capture controls off screen (FR-LIVE-02).
 */

import RecorderControl from '@/components/onboarding/RecorderControl';
import CaptureControl from '@/components/onboarding/CaptureControl';
import SnippetControl from '@/components/onboarding/SnippetControl';
import RecordingsLibrary from '@/components/onboarding/RecordingsLibrary';
import type { CapturedMedia, RecordingItem, UsageTag } from '@/lib/onboarding-sessions';

export interface RightRailProps {
  /** I-01: recording rows from the polling hook. */
  recordings?: RecordingItem[];
  /** I-01 + H-01: captured media from the polling hook. */
  captures?: CapturedMedia[];
  /** I-01: true when the user is Admin+ and may delete recordings. */
  canDelete?: boolean;
  /** Whether an active ConsentRecord exists for this session (F-01). */
  consentGranted?: boolean;
  /** F-03: passed to the recorder so it can open a MeetingRecording. */
  sessionId?: string | null;
  /** Opens the consent modal. AC-1: the disabled control still does this. */
  onRecordConsent?: () => void;
  /** H-01: called when a photo is captured and tagged. */
  onCapture?: (blob: Blob, tag: UsageTag, fileName?: string) => void;
  /** I-01: called after a recording is deleted so the parent can re-poll. */
  onRecordingDeleted?: () => void;
}

export default function RightRail({
  recordings = [],
  captures = [],
  canDelete = false,
  consentGranted = false,
  sessionId,
  onRecordConsent,
  onCapture,
  onRecordingDeleted,
}: RightRailProps) {
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
        <RecordingsLibrary
          recordings={recordings}
          captures={captures}
          canDelete={canDelete}
          onDeleted={onRecordingDeleted}
        />
      </div>
    </aside>
  );
}
