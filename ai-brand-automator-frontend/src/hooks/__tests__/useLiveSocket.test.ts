/**
 * #662 · the live socket's status must distinguish a drop from a first connect.
 *
 * This hook had no tests. It is also where a silent failure lives: when the
 * socket drops, the server cancels its STT task and nothing re-sends the
 * `start` frame that would spawn a new one, so transcription is over for the
 * rest of the meeting — while the recorder, the timer and the GCS upload all
 * carry on, because durability is independent of STT by design.
 *
 * `WebSocket` is supplied here because jsdom has none. That substitutes the
 * platform, not the hook: the reconnect logic under test runs for real.
 */

import { act, renderHook } from '@testing-library/react';

import { useLiveSocket } from '@/hooks/useLiveSocket';

const RECONNECT_DELAY_MS = 3000;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;
  static readonly CLOSED = 3;

  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  sent: unknown[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: unknown) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  /** What the browser does once the handshake completes. */
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  /** A network drop or a Cloud Run request-timeout cutting the socket. */
  drop() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

const latest = () => FakeWebSocket.instances.at(-1)!;

beforeEach(() => {
  // `doNotFake` the microtask APIs: Jest's modern fake timers replace
  // queueMicrotask, which stalls the promise chain `connect` is built from and
  // hangs the suite rather than failing it.
  jest.useFakeTimers({ doNotFake: ['queueMicrotask', 'nextTick', 'setImmediate'] });
  FakeWebSocket.instances = [];
  localStorage.setItem('access_token', 'test-token');
  Object.defineProperty(globalThis, 'WebSocket', {
    configurable: true,
    writable: true,
    value: FakeWebSocket,
  });
  global.fetch = jest.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ ticket: 'tkt-1' }),
  })) as unknown as typeof fetch;
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
  localStorage.clear();
});

function mountLive() {
  return renderHook(() =>
    useLiveSocket({ sessionId: 's-1', enabled: true, onFrame: () => {} }),
  );
}


/** Let the ticket POST and socket construction settle. */
async function flush(rounds = 8) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

/** Drive the retry timer, then settle the attempt it triggers. */
async function waitOutReconnect() {
  await act(async () => {
    jest.advanceTimersByTime(RECONNECT_DELAY_MS + 10);
  });
  await flush();
}

async function mountOpenLive() {
  const handle = mountLive();
  await flush();
  act(() => latest().open());
  return handle;
}

describe('#662 · a dropped socket is distinguishable from a first connect', () => {
  it('reports reconnecting — not connecting — after a drop', async () => {
    const { result } = await mountOpenLive();
    expect(result.current.status).toBe('live');

    act(() => latest().drop());

    // The distinction the banner depends on. Sharing 'connecting' with the
    // routine first connect is why the UI could show nothing for either.
    expect(result.current.status).toBe('reconnecting');
  });

  it('reports connecting on the first attempt, before anything has dropped', async () => {
    const { result } = mountLive();
    await flush();

    expect(FakeWebSocket.instances.length).toBe(1);
    expect(result.current.status).toBe('connecting');
  });

  it('ends at closed once the retries are exhausted', async () => {
    const { result } = await mountOpenLive();

    // Five reconnects is MAX_RECONNECT_ATTEMPTS. Each drop must actually
    // produce a new socket, which only driving the timer proves — with real
    // timers this would re-drop one dead socket and pass even if `connect` were
    // broken entirely.
    for (let i = 0; i < 5; i += 1) {
      act(() => latest().drop());
        await waitOutReconnect();
      expect(FakeWebSocket.instances.length).toBe(i + 2);
      act(() => latest().open());
    }

    act(() => latest().drop());

    expect(result.current.status).toBe('closed');
  });

  it('replays the start frame on reconnect, so transcription resumes', async () => {
    // The heart of #662. The server's STT task is cancelled with the socket and
    // only a `start` frame spawns another, so without this the socket returns,
    // reports 'live', and audio is silently dropped for the rest of the meeting.
    const { result } = await mountOpenLive();

    act(() =>
      result.current.sendControl({ type: 'start', recording_id: 'r-1', codec: 'opus' }),
    );
    const first = latest();
    expect(first.sent).toHaveLength(1);

    act(() => first.drop());
    await waitOutReconnect();
    act(() => latest().open());

    const replayed = JSON.parse(String(latest().sent[0]));
    expect(replayed).toMatchObject({ type: 'start', recording_id: 'r-1' });
  });

  it('does not replay start after the recording was stopped', async () => {
    // Replaying then would open an STT stream for a meeting that has ended.
    const { result } = await mountOpenLive();

    act(() => result.current.sendControl({ type: 'start', recording_id: 'r-1' }));
    act(() => result.current.sendControl({ type: 'stop' }));

    act(() => latest().drop());
    await waitOutReconnect();
    act(() => latest().open());

    expect(latest().sent).toHaveLength(0);
  });

  it('closes rather than hanging when the ticket cannot be minted', async () => {
    global.fetch = jest.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({}),
    })) as unknown as typeof fetch;

    const { result } = mountLive();
    await flush();

    // Not left on 'connecting': an operator watching a spinner forever cannot
    // tell that the meeting will never be transcribed.
    expect(result.current.status).toBe('closed');
    expect(FakeWebSocket.instances.length).toBe(0);
  });
});
