'use client';

/**
 * Enumerate audio input devices for multi-mic recording (O-01).
 *
 * Browsers gate device labels behind a getUserMedia grant: until the user
 * has allowed at least one mic, enumerateDevices returns ids but every
 * label is "". `unlockLabels` requests the minimum permission needed to
 * populate them, then immediately releases the stream.
 *
 * The `devicechange` event fires when mics are plugged or unplugged,
 * and the list refreshes automatically (AC-5).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface AudioDevice {
  deviceId: string;
  label: string;
  groupId: string;
}

export type MicRole = 'operator' | 'participant';

export interface MicAssignment {
  deviceId: string;
  label: string;
  role: MicRole;
  streamIndex: number;
}

export interface UseAudioDevices {
  devices: AudioDevice[];
  permissionGranted: boolean;
  error: string | null;
  unlockLabels: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useAudioDevices(): UseAudioDevices {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [permissionGranted, setPermissionGranted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const enumerate = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
      setError('Media devices not available in this browser');
      return;
    }
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      if (!mounted.current) return;
      const audioInputs = allDevices
        .filter((d) => d.kind === 'audioinput' && d.deviceId !== '')
        .map((d, i) => ({
          deviceId: d.deviceId,
          label: d.label || `Microphone ${i + 1}`,
          groupId: d.groupId,
        }));
      setDevices(audioInputs);
    } catch (err) {
      if (!mounted.current) return;
      setError(
        err instanceof Error ? err.message : 'Could not enumerate devices',
      );
    }
  }, []);

  const unlockLabels = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      if (!mounted.current) return;
      setPermissionGranted(true);
      setError(null);
      await enumerate();
    } catch {
      if (!mounted.current) return;
      setError('Microphone access denied. Allow it in your browser settings.');
    }
  }, [enumerate]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) return;
    const handler = () => void enumerate();
    navigator.mediaDevices.addEventListener('devicechange', handler);
    handler();
    return () =>
      navigator.mediaDevices.removeEventListener('devicechange', handler);
  }, [enumerate]);

  return { devices, permissionGranted, error, unlockLabels, refresh: enumerate };
}
