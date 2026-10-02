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

import { act, renderHook, waitFor } from '@testing-library/react';

import { useLiveSocket } from '@/hooks/useLiveSocket';

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
  jest.restoreAllMocks();
  localStorage.clear();
});

function mountLive() {
  return renderHook(() =>
    useLiveSocket({ sessionId: 's-1', enabled: true, onFrame: () => {} }),
  );
}

describe('#662 · a dropped socket is distinguishable from a first connect', () => {
  it('reports reconnecting — not connecting — after a drop', async () => {
    const { result } = mountLive();
    await waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    act(() => latest().open());
    await waitFor(() => expect(result.current.status).toBe('live'));

    act(() => latest().drop());

    // The distinction the banner depends on. Sharing 'connecting' with the
    // routine first connect is why the UI could show nothing for either.
    await waitFor(() => expect(result.current.status).toBe('reconnecting'));
  });

  it('reports connecting on the first attempt, before anything has dropped', async () => {
    const { result } = mountLive();

    await waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    expect(result.current.status).toBe('connecting');
  });

  it('ends at closed once the retries are exhausted', async () => {
    const { result } = mountLive();
    await waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    act(() => latest().open());
    await waitFor(() => expect(result.current.status).toBe('live'));

    // Five attempts is MAX_RECONNECT_ATTEMPTS; the sixth drop gives up.
    for (let i = 0; i < 6; i += 1) {
      act(() => latest().drop());
      await act(async () => {
        await Promise.resolve();
      });
    }

    await waitFor(() => expect(result.current.status).toBe('closed'));
  });

  it('closes rather than hanging when the ticket cannot be minted', async () => {
    global.fetch = jest.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({}),
    })) as unknown as typeof fetch;

    const { result } = mountLive();

    // Not left on 'connecting': an operator watching a spinner forever cannot
    // tell that the meeting will never be transcribed.
    await waitFor(() => expect(result.current.status).toBe('closed'));
    expect(FakeWebSocket.instances.length).toBe(0);
  });
});
