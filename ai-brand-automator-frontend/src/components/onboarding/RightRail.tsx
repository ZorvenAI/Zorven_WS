'use client';

/**
 * The meeting view's right rail (E-02, Design §11).
 *
 * RecorderControl, CaptureControl (H-01), SnippetControl (H-02) and
 * RecordingsLibrary (I-01) live here. The rail scrolls independently so a
 * long media list cannot push the capture controls off screen (FR-LIVE-02).
 */

import { Settings2 } from 'lucide-react';

import RecorderControl from '@/components/onboarding/RecorderControl';
import CaptureControl from '@/components/onboarding/CaptureControl';
import SnippetControl from '@/components/onboarding/SnippetControl';
import RecordingsLibrary from '@/components/onboarding/RecordingsLibrary';
import type { MicAssignment } from '@/hooks/useAudioDevices';
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
  /** F-04: forward binary audio to the live WebSocket for STT. */
  sendBinary?: (data: ArrayBuffer | Uint8Array) => void;
  /** F-04: send start/stop control frames to the live WebSocket. */
  sendControl?: (frame: Record<string, unknown>) => void;
  /** O-01: current mic assignments (lifted to MeetingView). */
  micAssignments?: MicAssignment[];
  /** O-01: opens the mic setup modal (lifted to MeetingView). */
  onOpenMicSetup?: () => void;
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
  sendBinary,
  sendControl,
  micAssignments = [],
  onOpenMicSetup,
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
        {consentGranted && onOpenMicSetup && (
          <button
            type="button"
            onClick={onOpenMicSetup}
            className="flex w-full items-center gap-2 rounded border border-white/15 px-3 py-2 text-sm text-white hover:border-brand-electric/40"
          >
            <Settings2 aria-hidden className="h-4 w-4 shrink-0 text-brand-silver" />
            {micAssignments.length > 0
              ? `${micAssignments.length} mic${micAssignments.length > 1 ? 's' : ''} configured`
              : 'Set up microphones'}
          </button>
        )}

        {consentGranted && micAssignments.length > 0 && (
          <div className="space-y-1">
            {micAssignments.map((a) => (
              <p key={a.deviceId} className="flex items-center gap-1.5 text-xs text-brand-silver">
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{
                    backgroundColor: a.role === 'operator' ? '#60a5fa' : '#34d399',
                  }}
                />
                <span className="truncate">{a.label}</span>
                <span className="ml-auto shrink-0 capitalize text-white/60">{a.role}</span>
              </p>
            ))}
          </div>
        )}

        <RecorderControl
          consentGranted={consentGranted}
          sessionId={sessionId}
          onRecordConsent={onRecordConsent}
          sendBinary={sendBinary}
          sendControl={sendControl}
          micAssignments={micAssignments}
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
