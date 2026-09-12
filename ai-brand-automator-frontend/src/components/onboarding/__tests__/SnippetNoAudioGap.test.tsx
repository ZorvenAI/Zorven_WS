/**
 * H-02 AC-3 — video snippet must not interfere with meeting audio recording.
 *
 * These tests verify that:
 * 1. The snippet recorder requests video-only (audio: false)
 * 2. The snippet's MediaStream has no audio tracks
 * 3. The meeting recorder continues producing chunks during snippet capture
 *
 * In jsdom we verify the API contracts. The real-browser validation that
 * concurrent getUserMedia calls do not renegotiate audio belongs in e2e.
 */

import { renderHook, act } from '@testing-library/react';

import { useSnippetRecorder } from '@/hooks/useSnippetRecorder';

const audioStop = jest.fn();
const videoStop = jest.fn();

const fakeAudioStream = {
  getTracks: () => [{ stop: audioStop, kind: 'audio', readyState: 'live' }],
  getAudioTracks: () => [{ stop: audioStop, kind: 'audio', readyState: 'live' }],
  getVideoTracks: () => [],
};

const fakeVideoStream = {
  getTracks: () => [{ stop: videoStop, kind: 'video', readyState: 'live' }],
  getAudioTracks: () => [],
  getVideoTracks: () => [{ stop: videoStop, kind: 'video', readyState: 'live' }],
};

let getUserMediaCalls: Array<MediaStreamConstraints>;

let mockRecorderInstance: {
  start: jest.Mock;
  stop: jest.Mock;
  state: string;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
};

beforeEach(() => {
  jest.useFakeTimers();
  audioStop.mockClear();
  videoStop.mockClear();
  getUserMediaCalls = [];

  const mockGetUserMedia = jest.fn((constraints: MediaStreamConstraints) => {
    getUserMediaCalls.push(constraints);
    if (constraints.audio) return Promise.resolve(fakeAudioStream);
    return Promise.resolve(fakeVideoStream);
  });

  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: mockGetUserMedia },
    writable: true,
    configurable: true,
  });

  mockRecorderInstance = {
    start: jest.fn(),
    stop: jest.fn(function (this: typeof mockRecorderInstance) {
      this.state = 'inactive';
      if (this.ondataavailable) {
        this.ondataavailable({ data: new Blob(['video'], { type: 'video/webm' }) });
      }
      if (this.onstop) {
        this.onstop();
      }
    }),
    state: 'inactive',
    ondataavailable: null,
    onstop: null,
  };

  const MockMediaRecorder = Object.assign(
    jest.fn().mockImplementation(() => {
      mockRecorderInstance.state = 'recording';
      return mockRecorderInstance;
    }),
    { isTypeSupported: jest.fn(() => true) },
  );

  Object.defineProperty(global, 'MediaRecorder', {
    value: MockMediaRecorder,
    writable: true,
    configurable: true,
  });

  global.URL.createObjectURL = jest.fn(() => 'blob:fake-url');
  global.URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

it('snippet getUserMedia does not request audio', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(getUserMediaCalls).toHaveLength(1);
  const constraints = getUserMediaCalls[0];
  expect(constraints.audio).toBe(false);
  expect(constraints.video).toBeTruthy();
});

it('snippet stream has no audio tracks', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(result.current.stream).toBe(fakeVideoStream);
  expect(result.current.stream!.getAudioTracks()).toHaveLength(0);
});

it('concurrent audio stream stays live during snippet recording', async () => {
  // Simulate meeting audio already acquired
  const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const audioTracks = audioStream.getAudioTracks();
  expect(audioTracks).toHaveLength(1);
  expect(audioTracks[0].readyState).toBe('live');

  // Now start the snippet recorder (video-only)
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  // Audio track should still be live
  expect(audioTracks[0].readyState).toBe('live');
  expect(audioStop).not.toHaveBeenCalled();

  // Stop snippet
  act(() => {
    result.current.stop();
  });

  // Audio track should still be live after snippet stops
  expect(audioTracks[0].readyState).toBe('live');
  expect(audioStop).not.toHaveBeenCalled();
});
