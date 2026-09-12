'use client';

/**
 * Mic selection and role assignment modal (O-01, Epic O).
 *
 * Lists every connected audio input device, lets the operator assign a role
 * (Operator / Participant / Not used) to each, and shows a live audio level
 * meter so they can verify each mic is picking up sound before recording
 * starts.
 *
 * Labels are permission-gated: browsers return "" for every label until the
 * user has granted mic access. The modal calls `unlockLabels` on mount to
 * resolve them (AC-4).
 */

import { useEffect, useRef, useState } from 'react';
import { Mic, Settings2, X } from 'lucide-react';

import {
  useAudioDevices,
  type MicAssignment,
  type MicRole,
} from '@/hooks/useAudioDevices';

export interface MicSetupProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: (assignments: MicAssignment[]) => void;
  existing?: MicAssignment[];
}

type RoleSelection = MicRole | 'none';

interface DeviceRow {
  deviceId: string;
  label: string;
  role: RoleSelection;
}

const ROLE_OPTIONS: { value: RoleSelection; label: string }[] = [
  { value: 'none', label: 'Not used' },
  { value: 'operator', label: 'Operator' },
  { value: 'participant', label: 'Participant' },
];

export default function MicSetup({
  open,
  onCancel,
  onConfirm,
  existing = [],
}: MicSetupProps) {
  const { devices, permissionGranted, error, unlockLabels } = useAudioDevices();
  const initialRoles = () => {
    const map: Record<string, RoleSelection> = {};
    for (const a of existing) map[a.deviceId] = a.role;
    return map;
  };
  const [roleMap, setRoleMap] = useState(initialRoles);
  const unlockAttempted = useRef(false);

  useEffect(() => {
    if (!open || permissionGranted || unlockAttempted.current) return;
    unlockAttempted.current = true;
    void unlockLabels();
  }, [open, permissionGranted, unlockLabels]);

  const rows: DeviceRow[] = devices.map((d) => ({
    deviceId: d.deviceId,
    label: d.label,
    role: roleMap[d.deviceId] ?? 'none',
  }));

  const assigned = rows.filter((r) => r.role !== 'none');

  function setRole(deviceId: string, role: RoleSelection) {
    setRoleMap((prev) => ({ ...prev, [deviceId]: role }));
  }

  function confirm() {
    const assignments: MicAssignment[] = assigned.map((r, i) => ({
      deviceId: r.deviceId,
      label: r.label,
      role: r.role as MicRole,
      streamIndex: i,
    }));
    onConfirm(assignments);
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="mic-setup-heading"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="glass-card w-full max-w-lg space-y-4 p-6">
        <div className="flex items-start justify-between gap-3">
          <h2
            id="mic-setup-heading"
            className="flex items-center gap-2 text-base font-semibold text-white"
          >
            <Settings2
              className="h-5 w-5 text-brand-electric"
              aria-hidden
            />
            Set up microphones
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="text-brand-silver hover:text-white"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <p className="text-sm text-brand-silver">
          Assign a role to each microphone. At least one must be assigned before
          you can proceed.
        </p>

        {error && (
          <p role="alert" className="text-sm text-rose-300">
            {error}
          </p>
        )}

        {!permissionGranted && !error && (
          <p className="text-sm text-amber-300">
            Requesting microphone access to detect devices…
          </p>
        )}

        {rows.length === 0 && permissionGranted && (
          <p className="text-sm text-brand-silver">
            No microphones detected. Connect a microphone and try again.
          </p>
        )}

        <div className="max-h-72 space-y-3 overflow-y-auto">
          {rows.map((row) => (
            <MicDeviceRow
              key={row.deviceId}
              deviceId={row.deviceId}
              label={row.label}
              role={row.role}
              onRoleChange={(role) => setRole(row.deviceId, role)}
              active={open && row.role !== 'none'}
            />
          ))}
        </div>

        <div className="flex items-center justify-between">
          <p className="text-xs text-brand-silver">
            {assigned.length === 0
              ? 'No microphones assigned'
              : `${assigned.length} microphone${assigned.length > 1 ? 's' : ''} assigned`}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded px-3 py-2 text-sm text-brand-silver hover:text-white"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={assigned.length === 0}
              className="btn-primary text-sm disabled:opacity-50"
            >
              Confirm setup
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MicDeviceRow({
  deviceId,
  label,
  role,
  onRoleChange,
  active,
}: {
  deviceId: string;
  label: string;
  role: RoleSelection;
  onRoleChange: (role: RoleSelection) => void;
  active: boolean;
}) {
  return (
    <div
      className={`rounded border p-3 ${
        role !== 'none'
          ? 'border-brand-electric/30 bg-brand-electric/5'
          : 'border-white/10'
      }`}
    >
      <div className="flex items-center gap-2">
        <Mic
          className={`h-4 w-4 shrink-0 ${
            role !== 'none' ? 'text-brand-electric' : 'text-brand-silver'
          }`}
          aria-hidden
        />
        <span className="flex-1 truncate text-sm text-white">{label}</span>
        <select
          value={role}
          onChange={(e) => onRoleChange(e.target.value as RoleSelection)}
          className="rounded border border-white/15 bg-transparent px-2 py-1 text-xs text-white"
        >
          {ROLE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-gray-900">
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {active && (
        <div className="mt-2">
          <AudioLevelMeter deviceId={deviceId} />
        </div>
      )}
    </div>
  );
}

function AudioLevelMeter({ deviceId }: { deviceId: string }) {
  const [level, setLevel] = useState(0);
  const rafRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let analyser: AnalyserNode | null = null;
    const dataArray = new Uint8Array(256);

    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { deviceId: { exact: deviceId } },
        });
        if (!mounted.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;

        const ctx = new AudioContext();
        ctxRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.5;
        source.connect(analyser);

        const tick = () => {
          if (!mounted.current || !analyser) return;
          analyser.getByteTimeDomainData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            const sample = (dataArray[i] - 128) / 128;
            sum += sample * sample;
          }
          const rms = Math.sqrt(sum / dataArray.length);
          setLevel(Math.min(rms * 4, 1));
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch {
        if (mounted.current) setLevel(0);
      }
    };

    void start();

    return () => {
      mounted.current = false;
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      void ctxRef.current?.close();
      ctxRef.current = null;
    };
  }, [deviceId]);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-brand-silver">Level</span>
      <div className="h-2 flex-1 rounded-full bg-white/10">
        <div
          className="h-full rounded-full transition-[width] duration-75"
          style={{
            width: `${level * 100}%`,
            backgroundColor:
              level > 0.7
                ? '#f87171'
                : level > 0.3
                  ? '#fbbf24'
                  : '#34d399',
          }}
        />
      </div>
    </div>
  );
}
