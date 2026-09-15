'use client';

/**
 * Voice roll call — attendance phase (O-05).
 *
 * After mic setup, the operator records each participant speaking their name.
 * The system transcribes the clip via STT and shows the detected name for
 * confirmation. Once all names are confirmed, attendance is persisted and the
 * meeting recording starts.
 *
 * AC-4: no manual text entry — voice or confirmation button only.
 * AC-5: roll call audio is captured but not stored long-term (ephemeral).
 */

import { useCallback, useRef, useState } from 'react';
import { Check, Loader2, Mic, RotateCcw, Users } from 'lucide-react';

import type { MicAssignment } from '@/hooks/useAudioDevices';
import { transcribeClip, recordAttendance, type Attendee } from '@/lib/onboarding-sessions';

export interface AttendanceRollCallProps {
  open: boolean;
  sessionId: string;
  micAssignments: MicAssignment[];
  onComplete: (attendees: Attendee[]) => void;
  onCancel: () => void;
}

type SlotState = 'idle' | 'recording' | 'transcribing' | 'confirmed';

interface RollCallSlot {
  assignment: MicAssignment;
  state: SlotState;
  detectedName: string;
}

const RECORD_DURATION_MS = 4000;

export default function AttendanceRollCall({
  open,
  sessionId,
  micAssignments,
  onComplete,
  onCancel,
}: AttendanceRollCallProps) {
  const [slots, setSlots] = useState<RollCallSlot[]>(() =>
    micAssignments.map((a) => ({
      assignment: a,
      state: 'idle',
      detectedName: '',
    })),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const updateSlot = useCallback(
    (index: number, patch: Partial<RollCallSlot>) => {
      setSlots((prev) => {
        const next = [...prev];
        next[index] = { ...next[index], ...patch };
        return next;
      });
    },
    [],
  );

  const startRecording = useCallback(
    async (index: number) => {
      const slot = slots[index];
      if (!slot) return;
      setError(null);
      updateSlot(index, { state: 'recording', detectedName: '' });

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { deviceId: { exact: slot.assignment.deviceId } },
        });

        const recorder = new MediaRecorder(stream, {
          mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : 'audio/webm',
        });
        recorderRef.current = recorder;
        const chunks: Blob[] = [];

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };

        recorder.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: recorder.mimeType });
          updateSlot(index, { state: 'transcribing' });

          try {
            const text = await transcribeClip(sessionId, blob, recorder.mimeType);
            updateSlot(index, {
              state: 'confirmed',
              detectedName: text || slot.assignment.label,
            });
          } catch {
            updateSlot(index, {
              state: 'confirmed',
              detectedName: slot.assignment.label,
            });
            setError('Could not transcribe — using mic label as fallback.');
          }
        };

        recorder.start();
        setTimeout(() => {
          if (recorder.state === 'recording') {
            recorder.stop();
          }
        }, RECORD_DURATION_MS);
      } catch {
        updateSlot(index, { state: 'idle' });
        setError('Microphone access denied.');
      }
    },
    [slots, sessionId, updateSlot],
  );

  const resetSlot = useCallback(
    (index: number) => {
      updateSlot(index, { state: 'idle', detectedName: '' });
    },
    [updateSlot],
  );

  const allConfirmed = slots.length > 0 && slots.every((s) => s.state === 'confirmed');

  const confirmAll = useCallback(async () => {
    setSaving(true);
    setError(null);
    const attendees: Attendee[] = slots.map((s) => ({
      name: s.detectedName,
      role: s.assignment.role,
      stream_index: s.assignment.streamIndex,
      mic_label: s.assignment.label,
    }));

    try {
      const result = await recordAttendance(sessionId, attendees);
      onComplete(result.attendees);
    } catch {
      setError('Could not save attendance. Try again.');
    } finally {
      setSaving(false);
    }
  }, [slots, sessionId, onComplete]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="roll-call-heading"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="glass-card w-full max-w-lg space-y-4 p-6">
        <h2
          id="roll-call-heading"
          className="flex items-center gap-2 text-base font-semibold text-white"
        >
          <Users className="h-5 w-5 text-brand-electric" aria-hidden />
          Voice Roll Call
        </h2>

        <p className="text-sm text-brand-silver">
          Record each participant saying their name. The system will detect and
          show the name for your confirmation.
        </p>

        {error && (
          <p role="alert" className="text-sm text-rose-300">
            {error}
          </p>
        )}

        <div className="max-h-72 space-y-3 overflow-y-auto">
          {slots.map((slot, i) => (
            <RollCallRow
              key={slot.assignment.deviceId}
              slot={slot}
              onRecord={() => startRecording(i)}
              onReset={() => resetSlot(i)}
            />
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded px-3 py-2 text-sm text-brand-silver hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirmAll}
            disabled={!allConfirmed || saving}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="mr-1 inline h-4 w-4 animate-spin" aria-hidden />
                Saving…
              </>
            ) : (
              'Confirm & start recording'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function RollCallRow({
  slot,
  onRecord,
  onReset,
}: {
  slot: RollCallSlot;
  onRecord: () => void;
  onReset: () => void;
}) {
  const { assignment, state, detectedName } = slot;

  return (
    <div
      data-testid={`roll-call-slot-${assignment.streamIndex}`}
      className={`rounded border p-3 ${
        state === 'confirmed'
          ? 'border-emerald-500/30 bg-emerald-500/5'
          : 'border-white/10'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Mic
            className={`h-4 w-4 shrink-0 ${
              state === 'recording'
                ? 'animate-pulse text-rose-400'
                : state === 'confirmed'
                  ? 'text-emerald-400'
                  : 'text-brand-silver'
            }`}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="truncate text-sm text-white">
              {assignment.label}
            </p>
            <p className="text-xs text-brand-silver capitalize">
              {assignment.role}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {state === 'idle' && (
            <button
              type="button"
              onClick={onRecord}
              className="flex items-center gap-1 rounded border border-brand-electric/30 bg-brand-electric/10 px-2 py-1 text-xs text-brand-electric hover:bg-brand-electric/20"
            >
              <Mic className="h-3 w-3" aria-hidden />
              Record name
            </button>
          )}
          {state === 'recording' && (
            <span className="flex items-center gap-1 text-xs text-rose-300">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-rose-400" />
              Listening…
            </span>
          )}
          {state === 'transcribing' && (
            <span className="flex items-center gap-1 text-xs text-brand-silver">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              Detecting…
            </span>
          )}
          {state === 'confirmed' && (
            <div className="flex items-center gap-1">
              <span
                data-testid={`detected-name-${assignment.streamIndex}`}
                className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-300"
              >
                <Check className="mr-1 inline h-3 w-3" aria-hidden />
                {detectedName}
              </span>
              <button
                type="button"
                onClick={onReset}
                aria-label="Re-record"
                className="text-brand-silver hover:text-white"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
