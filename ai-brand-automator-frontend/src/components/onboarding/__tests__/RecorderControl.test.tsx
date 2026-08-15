/**
 * F-02 · microphone capture.
 *
 * The card names `test_permission_denied_returns_to_ready`,
 * `test_unsupported_codec_refuses_loudly` and `test_elapsed_from_audio_timeline`.
 *
 * jsdom implements none of MediaRecorder, getUserMedia or AudioContext, so
 * they are supplied here. That is substituting the *platform*, which is the
 * same move as pointing the Google client at a local HTTP server — the code
 * under test is the hook, and it runs for real. What a substitute cannot
 * settle is whether Chromium actually produces opus at the cadence we asked
 * for; `e2e/recorder.spec.ts` answers that in a real browser with a fake
 * capture device, because a jsdom assertion there would only confirm that I
 * passed the arguments I meant to pass.
 */

import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import RecorderControl, {
  formatElapsed,
} from '@/components/onboarding/RecorderControl';
import {
  BLOCKED_MESSAGE,
  TIMESLICE_MS,
  UNSUPPORTED_MESSAGE,
  useMeetingRecorder,
} from '@/hooks/useMeetingRecorder';

/** A MediaRecorder that behaves like one, so the hook's logic runs unchanged. */
class FakeMediaRecorder {
  static supported: string[] = ['audio/webm;codecs=opus'];
  static instances: FakeMediaRecorder[] = [];

  static isTypeSupported(type: string) {
    return FakeMediaRecorder.supported.includes(type);
  }

  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  timeslice: number | null = null;

  constructor(
    public stream: unknown,
    public options: { mimeType: string },
  ) {
    FakeMediaRecorder.instances.push(this);
  }

  start(timeslice?: number) {
    this.timeslice = timeslice ?? null;
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.onstop?.();
  }

  /** What the browser does every `timeslice` ms. */
  emit(bytes = 8) {
    this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)]) });
  }
}

/** An audio clock the test drives, independent of Date.now(). */
class FakeAudioContext {
  static now = 0;
  static closed = 0;
  get currentTime() {
    return FakeAudioContext.now;
  }
  close() {
    FakeAudioContext.closed += 1;
    return Promise.resolve();
  }
}

let grant: () => Promise<unknown>;

beforeEach(() => {
  FakeMediaRecorder.supported = ['audio/webm;codecs=opus'];
  FakeMediaRecorder.instances = [];
  FakeAudioContext.now = 0;
  FakeAudioContext.closed = 0;

  grant = async () => ({
    getTracks: () => [{ stop: () => {} }],
  });

  Object.defineProperty(globalThis, 'MediaRecorder', {
    configurable: true,
    writable: true,
    value: FakeMediaRecorder,
  });
  Object.defineProperty(globalThis, 'AudioContext', {
    configurable: true,
    writable: true,
    value: FakeAudioContext,
  });
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    writable: true,
    value: { getUserMedia: () => grant() },
  });
});

const latest = () => FakeMediaRecorder.instances.at(-1)!;

// ── AC-1 · permission ────────────────────────────────────────────────

describe('AC-1 · permission is requested once and handled honestly', () => {
  it('test_permission_denied_returns_to_ready', async () => {
    /**
     * The card's named case, and the trap it names: "with the record control
     * returned to its ready state, not a spinner". A denied prompt does not
     * reappear on its own, so a control stuck mid-request is a dead end the
     * operator cannot even retry from — they would have to reload the page to
     * discover that is what happened.
     */
    grant = async () => {
      throw Object.assign(new Error('Permission denied'), {
        name: 'NotAllowedError',
      });
    };
    const { result } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());

    expect(result.current.state).toBe('blocked');
    expect(result.current.error).toBe(BLOCKED_MESSAGE);
    // Ready again: not 'requesting', and pressable.
    expect(result.current.state).not.toBe('requesting');
  });

  it('shows the denial and leaves the button usable', async () => {
    grant = async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    };
    const user = userEvent.setup();
    render(<RecorderControl consentGranted />);

    await user.click(screen.getByRole('button', { name: /start recording/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /microphone blocked/i,
    );
    const button = screen.getByRole('button', { name: /start recording/i });
    expect(button).toBeEnabled();
  });

  it('grants and records on a second press after a denial', async () => {
    /** The retry the criterion is protecting. If the first denial poisoned the
     *  control, this is what an operator could not do. */
    grant = async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    };
    const { result } = renderHook(() => useMeetingRecorder());
    await act(() => result.current.start());
    expect(result.current.state).toBe('blocked');

    grant = async () => ({ getTracks: () => [{ stop: () => {} }] });
    await act(() => result.current.start());

    expect(result.current.state).toBe('recording');
  });
});

// ── AC-2 · the format the pipeline expects ───────────────────────────

describe('AC-2 · capture produces the format the pipeline expects', () => {
  it('test_unsupported_codec_refuses_loudly', async () => {
    /**
     * The card's named case. Recording in a codec §4.3's adapter cannot read
     * would produce a whole meeting of audio that fails at transcription — an
     * hour after the operator could have done anything about it.
     */
    FakeMediaRecorder.supported = ['audio/mp4'];
    const { result } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());

    expect(result.current.state).toBe('unsupported');
    expect(result.current.error).toBe(UNSUPPORTED_MESSAGE);
    // And it never asked for the microphone, which is the point of checking
    // first: no permission prompt for a recording that cannot happen.
    expect(FakeMediaRecorder.instances).toHaveLength(0);
  });

  it('asks for opus and an explicit timeslice', async () => {
    const { result } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());

    expect(latest().options.mimeType).toBe('audio/webm;codecs=opus');
    // Not the default. MediaRecorder's default fires ondataavailable once, at
    // stop — a 45-minute meeting would arrive as one blob with nothing to
    // stream, and F-03's chunking depends on the cadence.
    expect(latest().timeslice).toBe(TIMESLICE_MS);
  });

  it('accepts the ogg container when that is what the browser offers', async () => {
    /**
     * Firefox packages opus in Ogg, Chromium in WebM. Choosing between
     * containers is not the fallback AC-2 forbids — that is falling back to a
     * different *codec*, which the test above covers.
     */
    FakeMediaRecorder.supported = ['audio/ogg;codecs=opus'];
    const { result } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());

    expect(result.current.state).toBe('recording');
    expect(latest().options.mimeType).toBe('audio/ogg;codecs=opus');
  });
});

// ── AC-3 · the state is unambiguous ──────────────────────────────────

describe('AC-3 · recording state is unambiguous at a glance', () => {
  it('test_elapsed_from_audio_timeline', async () => {
    /**
     * The card's named case, and FR-REC-02's rule: "elapsed time derives from
     * the audio timeline, not wall-clock, so a stalled tab does not report
     * phantom duration".
     *
     * Both halves are asserted, because only the pair distinguishes the two
     * clocks: the audio clock advancing moves the timer, and wall-clock
     * advancing on its own does not. A test that only advanced both together
     * would pass against Date.now().
     */
    // Fake timers *before* start(): the hook's ticker is a setInterval, and one
    // created under real timers is not advanced by advanceTimersByTime. The
    // first version of this test installed them afterwards and measured
    // nothing at all.
    jest.useFakeTimers();
    try {
      const { result } = renderHook(() => useMeetingRecorder());
      await act(() => result.current.start());
      const wallClockStart = Date.now();

      // The machine sleeps: wall-clock jumps ten minutes, audio does not.
      jest.setSystemTime(wallClockStart + 600_000);
      await act(async () => {
        jest.advanceTimersByTime(1000);
      });
      expect(result.current.elapsedSeconds).toBeLessThan(1);

      // Now the audio clock moves, and only then does the timer.
      FakeAudioContext.now = 42.5;
      await act(async () => {
        jest.advanceTimersByTime(1000);
      });
      expect(result.current.elapsedSeconds).toBeCloseTo(42.5, 1);
    } finally {
      jest.useRealTimers();
    }
  });

  it('shows a recording indicator with the elapsed time', async () => {
    const user = userEvent.setup();
    render(<RecorderControl consentGranted />);

    await user.click(screen.getByRole('button', { name: /start recording/i }));

    const indicator = await screen.findByRole('status');
    expect(indicator).toHaveTextContent(/recording/i);
    expect(screen.getByTestId('elapsed')).toHaveTextContent('00:00');
    expect(
      screen.getByRole('button', { name: /stop recording/i }),
    ).toBeInTheDocument();
  });

  it('puts the recording state in the tab title', async () => {
    /** AC-3: "so a backgrounded tab is still obvious" — the one indicator that
     *  survives the operator switching away, which is when forgetting is most
     *  likely. */
    document.title = 'Zorven';
    const { result, unmount } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());
    expect(document.title).toMatch(/recording/i);

    unmount();
    expect(document.title).toBe('Zorven');
  });

  it.each([
    [0, '00:00'],
    [7.4, '00:07'],
    [61, '01:01'],
    [2705, '45:05'],
  ])('renders %ss as %s', (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected);
  });
});

// ── AC-4 · stopping is safe ──────────────────────────────────────────

describe('AC-4 · stopping is safe', () => {
  it('keeps every chunk, in arrival order, after stop', async () => {
    /** F-03 drains this queue. A dropped chunk is a hole in the recording that
     *  nothing downstream can reconstruct. */
    const { result } = renderHook(() => useMeetingRecorder());
    await act(() => result.current.start());

    await act(async () => {
      latest().emit(4);
      latest().emit(8);
      latest().emit(16);
    });
    await act(() => result.current.stop());

    expect(result.current.chunks.map((chunk) => chunk.index)).toEqual([0, 1, 2]);
    expect(result.current.chunks.map((chunk) => chunk.blob.size)).toEqual([4, 8, 16]);
  });

  it('registers a tab-close warning only while recording', async () => {
    /**
     * AC-4 wants the confirmation during a recording. A permanently installed
     * handler would warn on every navigation away from a meeting that was
     * never recording, which is how operators learn to click through the
     * dialog without reading it.
     */
    const added: string[] = [];
    const removed: string[] = [];
    const addSpy = jest
      .spyOn(window, 'addEventListener')
      .mockImplementation((type: string, ...rest: unknown[]) => {
        added.push(type);
        // @ts-expect-error - passing through to the real implementation
        return EventTarget.prototype.addEventListener.call(window, type, ...rest);
      });
    const removeSpy = jest
      .spyOn(window, 'removeEventListener')
      .mockImplementation((type: string, ...rest: unknown[]) => {
        removed.push(type);
        // @ts-expect-error - passing through to the real implementation
        return EventTarget.prototype.removeEventListener.call(window, type, ...rest);
      });

    try {
      const { result } = renderHook(() => useMeetingRecorder());
      expect(added).not.toContain('beforeunload');

      await act(() => result.current.start());
      expect(added).toContain('beforeunload');

      await act(() => result.current.stop());
      expect(removed).toContain('beforeunload');
    } finally {
      addSpy.mockRestore();
      removeSpy.mockRestore();
    }
  });

  it('releases the microphone and the audio context on stop', async () => {
    /** A live track keeps the browser's recording pip lit after the operator
     *  pressed stop, which says we are still listening when we are not. */
    const stopped: string[] = [];
    grant = async () => ({
      getTracks: () => [{ stop: () => stopped.push('track') }],
    });
    const { result } = renderHook(() => useMeetingRecorder());

    await act(() => result.current.start());
    await act(() => result.current.stop());

    expect(stopped).toEqual(['track']);
    expect(FakeAudioContext.closed).toBe(1);
    expect(result.current.state).toBe('idle');
  });

  it('reads the final elapsed before the audio context is closed', async () => {
    /** currentTime is meaningless after close(), and this is the value B-08's
     *  duration_s comes from. Reading it in the wrong order silently reports
     *  zero for every recording. */
    const { result } = renderHook(() => useMeetingRecorder());
    await act(() => result.current.start());
    FakeAudioContext.now = 128.25;

    await act(() => result.current.stop());

    await waitFor(() => expect(result.current.elapsedSeconds).toBeCloseTo(128.25, 1));
  });
});
