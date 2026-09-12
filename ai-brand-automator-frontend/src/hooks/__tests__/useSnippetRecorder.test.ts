/**
 * H-02 · useSnippetRecorder hook tests.
 *
 * jsdom has no MediaRecorder or getUserMedia, so both are mocked.
 * The tests verify the hook's state machine, auto-stop, and countdown logic.
 */

import { renderHook, act } from '@testing-library/react';
import {
  useSnippetRecorder,
  SNIPPET_MAX_SECONDS,
  SNIPPET_COUNTDOWN_FROM,
  supportedVideoMimeType,
} from '@/hooks/useSnippetRecorder';

const fakeStop = jest.fn();
const fakeStream = {
  getTracks: () => [{ stop: fakeStop }],
  getAudioTracks: () => [],
  getVideoTracks: () => [{ stop: fakeStop, readyState: 'live' }],
};

let mockRecorderInstance: {
  start: jest.Mock;
  stop: jest.Mock;
  state: string;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
};

beforeEach(() => {
  jest.useFakeTimers();
  fakeStop.mockClear();

  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: jest.fn().mockResolvedValue(fakeStream),
    },
    writable: true,
    configurable: true,
  });

  mockRecorderInstance = {
    start: jest.fn(),
    stop: jest.fn(function (this: typeof mockRecorderInstance) {
      this.state = 'inactive';
      if (this.ondataavailable) {
        this.ondataavailable({ data: new Blob(['video-data'], { type: 'video/webm' }) });
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
    {
      isTypeSupported: jest.fn((type: string) =>
        type === 'video/webm' || type === 'video/webm;codecs=vp8',
      ),
    },
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

it('starts idle', () => {
  const { result } = renderHook(() => useSnippetRecorder());
  expect(result.current.state).toBe('idle');
  expect(result.current.videoBlob).toBeNull();
  expect(result.current.stream).toBeNull();
});

it('starts with video-only getUserMedia (audio: false)', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
    video: { facingMode: 'environment' },
    audio: false,
  });
});

it('transitions to recording state on start', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(result.current.state).toBe('recording');
  expect(result.current.stream).toBe(fakeStream);
});

it('auto-stop fires at SNIPPET_MAX_SECONDS', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(result.current.state).toBe('recording');

  act(() => {
    jest.advanceTimersByTime(SNIPPET_MAX_SECONDS * 1000);
  });

  expect(result.current.state).toBe('stopped');
  expect(result.current.videoBlob).not.toBeNull();
});

it('countdown ticks from SNIPPET_COUNTDOWN_FROM', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  // Before countdown window: remaining is null
  expect(result.current.secondsRemaining).toBeNull();

  // Advance to when countdown should start (30 - 10 = 20s)
  act(() => {
    jest.advanceTimersByTime((SNIPPET_MAX_SECONDS - SNIPPET_COUNTDOWN_FROM) * 1000);
  });

  expect(result.current.secondsRemaining).not.toBeNull();
  expect(result.current.secondsRemaining).toBeLessThanOrEqual(SNIPPET_COUNTDOWN_FROM);
});

it('stop produces a blob', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  act(() => {
    result.current.stop();
  });

  expect(result.current.state).toBe('stopped');
  expect(result.current.videoBlob).toBeInstanceOf(Blob);
});

it('reset clears state', async () => {
  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  act(() => {
    result.current.stop();
  });

  expect(result.current.state).toBe('stopped');

  act(() => {
    result.current.reset();
  });

  expect(result.current.state).toBe('idle');
  expect(result.current.videoBlob).toBeNull();
  expect(result.current.stream).toBeNull();
  expect(result.current.elapsedSeconds).toBe(0);
  expect(result.current.secondsRemaining).toBeNull();
});

it('unsupported browser sets error', async () => {
  (MediaRecorder.isTypeSupported as jest.Mock).mockReturnValue(false);

  const { result } = renderHook(() => useSnippetRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(result.current.state).toBe('unsupported');
  expect(result.current.error).toBeTruthy();
});

it('supportedVideoMimeType returns first supported type', () => {
  const type = supportedVideoMimeType();
  expect(type).toBe('video/webm;codecs=vp8');
});

it('supportedVideoMimeType returns null when nothing supported', () => {
  (MediaRecorder.isTypeSupported as jest.Mock).mockReturnValue(false);
  expect(supportedVideoMimeType()).toBeNull();
});
