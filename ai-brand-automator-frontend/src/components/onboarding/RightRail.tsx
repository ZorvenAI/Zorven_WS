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
}

const CONTROLS = [
  { icon: Mic, label: 'Start recording', owner: 'F-02' },
  { icon: Camera, label: 'Capture photo', owner: 'H-01' },
  { icon: Video, label: 'Capture video', owner: 'H-02' },
] as const;

export default function RightRail({ recordingCount = 0 }: RightRailProps) {
  return (
    <aside
      aria-labelledby="rail-heading"
      className="glass-card flex min-h-0 flex-col p-5"
    >
      <h2 id="rail-heading" className="text-sm font-semibold text-white">
        Recordings and captures
      </h2>

      <div className="mt-3 space-y-2">
        {CONTROLS.map(({ icon: Icon, label }) => (
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
