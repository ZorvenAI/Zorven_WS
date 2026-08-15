'use client';

/**
 * The meeting view's right rail (E-02, Design §11).
 *
 * Shells only. §11 gives the rail to RecorderControl, CaptureControl and
 * RecordingsLibrary, and each of those is its own story — F-02, H-01 and
 * I-01 respectively. What E-02 owes them is a place to attach that is already
 * the right shape and already scrolls independently.
 *
 * The controls are rendered disabled rather than omitted, following the
 * precedent E-01 set and for the same reason: a greyed control tells the
 * operator the capability exists and is not ready, where an absent one reads
 * as a missing feature. They carry an explicit reason so the state is legible
 * rather than mysterious.
 */

import { Camera, Mic, Video } from 'lucide-react';

export interface RightRailProps {
  /** Placeholder count until I-01 lists real recordings. */
  recordingCount?: number;
  /** Whether an active ConsentRecord exists for this session (F-01). */
  consentGranted?: boolean;
  /** Opens the consent modal. AC-1: the disabled control still does this. */
  onRecordConsent?: () => void;
}

const CAPTURE_CONTROLS = [
  { icon: Camera, label: 'Capture photo', owner: 'H-01' },
  { icon: Video, label: 'Capture video', owner: 'H-02' },
] as const;

export default function RightRail({
  recordingCount = 0,
  consentGranted = false,
  onRecordConsent,
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
        {/*
          AC-1: "the record control is visible but disabled, with the reason
          stated inline — 'Record consent to enable recording' — rather than as
          an unexplained grey button. And clicking it opens the consent modal
          rather than doing nothing."
          
          So it is not `disabled`. A disabled button cannot be clicked, cannot
          be focused and is skipped by a screen reader's button list, which
          would make the second half of that criterion impossible. `aria-disabled`
          says "this will not do what it says yet" while leaving it reachable —
          the same distinction QuestionChecklist landed on in #566.
        */}
        <button
          type="button"
          aria-disabled={!consentGranted}
          onClick={consentGranted ? undefined : onRecordConsent}
          className={`flex w-full items-center gap-2 rounded border px-3 py-2 text-sm ${
            consentGranted
              ? 'border-white/10 text-brand-silver opacity-60'
              : 'border-brand-electric/40 text-white'
          }`}
          title={
            consentGranted
              ? 'Available once live capture ships'
              : 'Record consent to enable recording'
          }
        >
          <Mic aria-hidden="true" className="h-4 w-4 shrink-0" />
          Start recording
        </button>
        {!consentGranted && (
          // Inline, not a tooltip. AC-1 asks for the reason *stated*, and a
          // title attribute is invisible to touch and to most screen readers.
          <p className="text-xs text-amber-300">
            Record consent to enable recording
          </p>
        )}

        {CAPTURE_CONTROLS.map(({ icon: Icon, label }) => (
          <button
            key={label}
            type="button"
            disabled
            // The reason travels with the control. "Not available yet" on its
            // own invites a support ticket asking when.
            title="Available once live capture ships"
            className="flex w-full items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm text-brand-silver opacity-60"
          >
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
            {label}
          </button>
        ))}
      </div>

      <div
        data-testid="rail-scroller"
        // AC-1: the rail scrolls on its own. A long recordings list must not
        // push the capture controls off the top — they are the reason the rail
        // is "always reachable" in FR-LIVE-02.
        className="mt-4 min-h-0 flex-1 overflow-y-auto"
      >
        {recordingCount === 0 ? (
          <p className="text-sm text-brand-silver">
            Recordings and captured media appear here during the meeting.
          </p>
        ) : (
          <p className="text-sm text-brand-silver">
            {recordingCount} item{recordingCount === 1 ? '' : 's'}
          </p>
        )}
      </div>
    </aside>
  );
}
