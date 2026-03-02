/**
 * useVoiceInput — hold-to-talk speech-to-text for the chat input.
 *
 * Supports two engines:
 *   1. **Web Speech API** (Chrome/Edge/Safari) — browser-native, free,
 *      zero latency.  Used automatically when available.
 *   2. **Cloud fallback** (Firefox, etc.) — records audio via
 *      MediaRecorder and POSTs the blob to the Django backend which
 *      transcribes it using Gemini 2.0 Flash.
 *
 * The hook returns a `transcript` string that the consumer should
 * append to the textarea and then call `reset()`.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/lib/api';

type Engine = 'webspeech' | 'cloud' | null;

export interface UseVoiceInputReturn {
  /** Whether any speech input method is available. */
  isSupported: boolean;
  /** Which engine is active: 'webspeech' | 'cloud' | null */
  engine: Engine;
  /** Currently recording / listening. */
  isListening: boolean;
  /** Cloud path: audio is being sent to the backend for transcription. */
  isTranscribing: boolean;
  /** The latest transcribed text. Consumer should read, use, then reset(). */
  transcript: string;
  /** Human-readable error (e.g. "Microphone access denied"). */
  error: string | null;
  /** Start listening — call on mouseDown / touchStart. */
  startListening: () => void;
  /** Stop listening — call on mouseUp / touchEnd. */
  stopListening: () => void;
  /** Clear transcript and error state. */
  reset: () => void;
}

function detectEngine(): Engine {
  if (typeof window === 'undefined') return null;
  if (window.SpeechRecognition || window.webkitSpeechRecognition) {
    return 'webspeech';
  }
  if (typeof navigator.mediaDevices?.getUserMedia === 'function') {
    return 'cloud';
  }
  return null;
}

export function useVoiceInput(): UseVoiceInputReturn {
  const [engine, setEngine] = useState<Engine>(null);
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Refs survive across renders without triggering re-renders.
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordStartRef = useRef<number>(0);

  // ── Engine detection (runs once after mount) ──
  useEffect(() => {
    setEngine(detectEngine());
  }, []);

  const isSupported = engine !== null;

  // ── Cleanup on unmount ──
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      mediaRecorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ── Web Speech API helpers ──
  const startWebSpeech = useCallback(() => {
    const SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // Accumulate all final results across the session so long
      // recordings aren't cut off after the first pause.
      const parts: string[] = [];
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          parts.push(event.results[i][0].transcript);
        }
      }
      if (parts.length > 0) setTranscript(parts.join(' '));
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // "aborted" fires when we call stop() — not a real error.
      if (event.error === 'aborted') return;
      const messages: Record<string, string> = {
        'not-allowed': 'Microphone access denied. Check browser permissions.',
        'no-speech': 'No speech detected. Please try again.',
        'network': 'Network error during speech recognition.',
      };
      setError(messages[event.error] ?? `Speech error: ${event.error}`);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
      setIsListening(true);
      setError(null);
    } catch {
      setError('Failed to start speech recognition.');
    }
  }, []);

  const stopWebSpeech = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  // ── Cloud (MediaRecorder) helpers ──
  const startCloudRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg';
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      recordStartRef.current = Date.now();

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      setIsListening(true);
      setError(null);
    } catch {
      setError('Microphone access denied. Check browser permissions.');
    }
  }, []);

  const stopCloudRecording = useCallback(async () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      setIsListening(false);
      return;
    }

    // Wait for the recorder to actually stop and fire ondataavailable.
    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const mimeType = recorder.mimeType || 'audio/webm';
        resolve(new Blob(chunksRef.current, { type: mimeType }));
      };
      recorder.stop();
    });

    // Release mic immediately.
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setIsListening(false);

    // Ignore accidental taps (< 500ms).
    const duration = Date.now() - recordStartRef.current;
    if (duration < 500) return;

    // Transcribe via backend.
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      formData.append('audio', blob, `recording.${blob.type.split('/')[1]}`);
      const res = await apiClient.upload('/ai/speech-to-text/', formData);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          (body as Record<string, string>).error || `HTTP ${res.status}`,
        );
      }
      const data = (await res.json()) as { transcript: string };
      if (data.transcript) setTranscript(data.transcript);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Transcription failed.',
      );
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  // ── Public API ──
  const startListening = useCallback(() => {
    if (isListening || isTranscribing) return;
    if (engine === 'webspeech') startWebSpeech();
    else if (engine === 'cloud') startCloudRecording();
  }, [engine, isListening, isTranscribing, startWebSpeech, startCloudRecording]);

  const stopListening = useCallback(() => {
    if (engine === 'webspeech') stopWebSpeech();
    else if (engine === 'cloud') stopCloudRecording();
  }, [engine, stopWebSpeech, stopCloudRecording]);

  const reset = useCallback(() => {
    setTranscript('');
    setError(null);
  }, []);

  return {
    isSupported,
    engine,
    isListening,
    isTranscribing,
    transcript,
    error,
    startListening,
    stopListening,
    reset,
  };
}
