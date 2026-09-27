/**
 * O-07 · per-stream upload sessions.
 *
 * The regression these tests exist for: before this story the hook absorbed
 * every chunk in `chunksRef` regardless of which mic produced it, so a two-mic
 * meeting PUT both mics' opus bytes into one GCS object — interleaved, and
 * undecodable. AC-1 is therefore not "add a feature" but "stop corrupting the
 * archive", and the first test below is the one that would have caught it.
 *
 * No mocks: the transport is a real in-memory `UploadTransport` that speaks the
 * resumable protocol's status codes, and `apiClient` is exercised against a
 * stubbed `fetch` at the network boundary rather than replaced.
 */

import { act, renderHook } from '@testing-library/react';

import {
  ALIGN_INTERVAL_MS,
  LOCAL_BOUND_BYTES,
  useChunkUploader,
} from '@/hooks/useChunkUploader';
import type { UploadTransport } from '@/lib/resumable-upload';

const ALIGN_BYTES = 262144;

/** Records which session URL each byte range was PUT to. */
function recordingTransport() {
  const sent: { url: string; size: number; final: boolean }[] = [];
  const committed = new Map<string, number>();
  const transport: UploadTransport = {
    async put(url, body, headers) {
      const final = !headers['Content-Range']?.endsWith('/*');
      sent.push({ url, size: body.size, final });
      const at = (committed.get(url) ?? 0) + body.size;
      committed.set(url, at);
      if (final) return { status: 200, range: null };
      return { status: 308, range: `bytes=0-${at - 1}` };
    },
  };
  return { transport, sent };
}

/** A transport whose nominated session URL always fails retryably. */
function failingTransport(failUrlSubstring: string) {
  const sent: { url: string; size: number }[] = [];
  const committed = new Map<string, number>();
  const transport: UploadTransport = {
    async put(url, body) {
      if (url.includes(failUrlSubstring)) {
        return { status: 503, range: null };
      }
      sent.push({ url, size: body.size });
      const at = (committed.get(url) ?? 0) + body.size;
      committed.set(url, at);
      return { status: 308, range: `bytes=0-${at - 1}` };
    },
  };
  return { transport, sent };
}

function blobOf(size: number): Blob {
  return new Blob([new Uint8Array(size)]);
}

/** Answers the upload-session endpoint, one URL per stream_index. */
function stubSessionEndpoint() {
  const requested: (number | null)[] = [];
  global.fetch = jest.fn(async (input: unknown, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const index = body.stream_index ?? null;
    requested.push(index);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        session_url:
          index === null
            ? 'https://upload.example/legacy'
            : `https://upload.example/stream-${index}`,
        degraded_message: 'Upload delayed — recording continues locally.',
      }),
    } as unknown as Response;
  }) as unknown as typeof fetch;
  return { requested };
}

beforeEach(() => {
  localStorage.setItem('access_token', 'test-token');
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

/**
 * Flush every stream once, through the same path the stop button takes.
 *
 * Real timers, driven by `finalise()` rather than by the 30 s cadence. Fake
 * timers are not an option here: Jest's modern implementation also fakes
 * `queueMicrotask`, so the promise chain this hook is built from never settles
 * and the suite hangs rather than failing. Driving the flush directly tests the
 * same routing and isolation, and `ALIGN_INTERVAL_MS` stays covered by the
 * F-03 suite that owns the cadence.
 */
async function flushAll(hook: { current: { finalise: () => Promise<void> } }) {
  await act(async () => {
    await hook.current.finalise();
  });
}

describe('O-07 AC-1 · each mic uploads to its own object', () => {
  it('routes a chunk tagged for an undeclared mic to a stream that is flushed', async () => {
    // Such a chunk used to land on a key that neither the cadence nor
    // `finalise` iterated, so its audio was silently dropped and excluded from
    // the byte counters — invisible until it alone crossed the bound.
    const { transport, sent } = recordingTransport();
    stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(1024), streamIndex: 0 },
      { blob: blobOf(2048), streamIndex: 7 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }],
        transport,
      }),
    );

    await flushAll(result);

    const total = sent.reduce((t, s) => t + s.size, 0);
    expect(total).toBe(1024 + 2048);
  });

  it('routes each mic to its own session instead of interleaving them', async () => {
    const { transport, sent } = recordingTransport();
    stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(ALIGN_BYTES), streamIndex: 0 },
      { blob: blobOf(ALIGN_BYTES), streamIndex: 1 },
    ];
    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
      }),
    );

    await flushAll(result);

    expect(sent.length).toBe(2);
    const byUrl = new Map(sent.map((s) => [s.url, s.size]));
    // The bug: one URL receiving both mics' bytes.
    expect(byUrl.size).toBe(2);
    expect(byUrl.get('https://upload.example/stream-0')).toBe(ALIGN_BYTES);
    expect(byUrl.get('https://upload.example/stream-1')).toBe(ALIGN_BYTES);
    expect(result.current.streams).toHaveLength(2);
  });

  it('asks the server for one session per mic', async () => {
    const { transport } = recordingTransport();
    const { requested } = stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(ALIGN_BYTES), streamIndex: 0 },
      { blob: blobOf(ALIGN_BYTES), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
      }),
    );

    await flushAll(result);

    expect(requested.length).toBe(2);
    expect(new Set(requested)).toEqual(new Set([0, 1]));
  });

  it('sends no stream_index for a single-mic recording', async () => {
    const { transport, sent } = recordingTransport();
    const { requested } = stubSessionEndpoint();
    const chunks = [{ blob: blobOf(ALIGN_BYTES) }];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        transport,
      }),
    );

    await flushAll(result);

    // The regression gate: the pre-O-07 request, unchanged.
    expect(requested).toEqual([null]);
    expect(sent[0].url).toBe('https://upload.example/legacy');
  });
});

describe('O-07 · every byte lands in exactly one stream', () => {
  /**
   * The property the interleaving bug violated. Over arbitrary arrival
   * orders, each mic's object must receive exactly that mic's bytes — no
   * duplication, no loss, and no cross-contamination.
   */
  it.each([
    [[0, 1, 0, 1]],
    [[1, 1, 0, 0]],
    [[0, 0, 0, 1]],
    [[1, 0, 1, 0, 1, 0]],
    [[0, 1, 2, 2, 1, 0]],
  ])('preserves per-stream totals for arrival order %j', async (order) => {
    const { transport, sent } = recordingTransport();
    stubSessionEndpoint();
    const indices = [...new Set(order)];
    const chunks = order.map((streamIndex) => ({
      blob: blobOf(ALIGN_BYTES),
      streamIndex,
    }));

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: indices.map((streamIndex) => ({ streamIndex })),
        transport,
      }),
    );

    await flushAll(result);

    expect(sent.length).toBe(indices.length);
    for (const index of indices) {
      const expected = order.filter((o) => o === index).length * ALIGN_BYTES;
      const actual = sent
        .filter((s) => s.url === `https://upload.example/stream-${index}`)
        .reduce((total, s) => total + s.size, 0);
      expect(actual).toBe(expected);
    }
    // No byte went anywhere else.
    const total = sent.reduce((t, s) => t + s.size, 0);
    expect(total).toBe(order.length * ALIGN_BYTES);
  });
});

describe('O-07 AC-3 · degraded mode is per stream', () => {
  it('keeps a healthy mic uploading while another fails', async () => {
    const { transport, sent } = failingTransport('stream-1');
    stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(ALIGN_BYTES), streamIndex: 0 },
      { blob: blobOf(ALIGN_BYTES), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
      }),
    );

    await flushAll(result);

    // Stream 0's bytes reached GCS even though stream 1 is failing: one mic's
    // outage must not cost us another participant's audio.
    expect(sent.some((s) => s.url.endsWith('stream-0'))).toBe(true);
    expect(sent.some((s) => s.url.endsWith('stream-1'))).toBe(false);

    const failing = result.current.streams.find((s) => s.streamIndex === 1);
    expect(failing?.status).toBe('delayed');
  });

  it('reports the worst stream status as the meeting status', async () => {
    const { transport } = failingTransport('stream-1');
    stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(ALIGN_BYTES), streamIndex: 0 },
      { blob: blobOf(ALIGN_BYTES), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
      }),
    );

    await flushAll(result);

    // One operator, one indicator: a half-failing meeting must not read as
    // healthy just because one mic is fine.
    expect(result.current.status).toBe('delayed');
  });
});

describe('O-07 AC-2 · the local bound is per stream', () => {
  it('stops the recording when any one mic exceeds its own bound', async () => {
    const { transport } = recordingTransport();
    stubSessionEndpoint();
    const onBoundReached = jest.fn();
    // Stream 1 alone is over the bound; stream 0 is well under it. A shared
    // allowance would have tripped on the sum instead.
    const chunks = [
      { blob: blobOf(1024), streamIndex: 0 },
      { blob: blobOf(LOCAL_BOUND_BYTES + 1), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
        onBoundReached,
      }),
    );

    expect(onBoundReached).toHaveBeenCalled();
    // The meeting is the unit: a transcript missing one participant from the
    // ten-minute mark is not the legal record O-06 assembles.
    expect(result.current.status).toBe('stopped');
    expect(result.current.message).toMatch(/could not be saved/);
    for (const stream of result.current.streams) {
      expect(stream.status).toBe('stopped');
    }
  });

  it('does not trip when each mic is individually under the bound', async () => {
    const { transport } = recordingTransport();
    stubSessionEndpoint();
    const onBoundReached = jest.fn();
    const half = Math.floor(LOCAL_BOUND_BYTES * 0.6);
    const chunks = [
      { blob: blobOf(half), streamIndex: 0 },
      { blob: blobOf(half), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
        onBoundReached,
      }),
    );

    // Their sum is over the bound; neither mic is. AC-2 is per stream.
    expect(onBoundReached).not.toHaveBeenCalled();
    expect(result.current.status).not.toBe('stopped');
  });
});

describe('F-03/O-07 · audio is appended during the meeting, not only at the end', () => {
  /**
   * The regression that mattered most, and the one `finalise`-driven tests
   * cannot see.
   *
   * `MediaRecorder` runs with a 20 ms timeslice, so `pendingBytes` changes
   * about fifty times a second per mic. While the cadence was a `setTimeout`
   * whose effect listed byte counters as dependencies, every chunk tore the
   * timer down and re-armed it at the full 30 s — so it never elapsed, no
   * incremental append ever ran, and the whole meeting sat in memory until the
   * stop button. A tab crash at minute nine lost all of it.
   *
   * `doNotFake` is required: Jest's modern fake timers also replace
   * `queueMicrotask`, which stalls the promise chain this hook is built from
   * and hangs the suite instead of failing it.
   */
  beforeEach(() => {
    jest.useFakeTimers({
      doNotFake: ['queueMicrotask', 'nextTick', 'setImmediate', 'Date'],
    });
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it('appends on the cadence even while chunks keep arriving', async () => {
    const { transport, sent } = recordingTransport();
    stubSessionEndpoint();
    const chunks = [{ blob: blobOf(ALIGN_BYTES), streamIndex: 0 }];
    const chunksRef = { current: chunks };

    const { rerender } = renderHook(
      ({ count }: { count: number }) =>
        useChunkUploader({
          recordingId: 'rec-1',
          chunksRef,
          chunkCount: count,
          recording: true,
          streams: [{ streamIndex: 0 }],
          transport,
        }),
      { initialProps: { count: chunks.length } },
    );

    // Chunks arrive *while* the cadence window is open, which is the part that
    // discriminates: a timer re-armed on each arrival never reaches its delay,
    // so advancing past the interval in steps with an arrival between each is
    // the shape of a real meeting rather than a quiet one.
    const step = ALIGN_INTERVAL_MS / 6;
    for (let i = 0; i < 7; i += 1) {
      chunks.push({ blob: blobOf(ALIGN_BYTES), streamIndex: 0 });
      await act(async () => {
        rerender({ count: chunks.length });
      });
      await act(async () => {
        jest.advanceTimersByTime(step);
      });
      for (let j = 0; j < 4; j += 1) {
        await act(async () => {
          await Promise.resolve();
        });
      }
    }

    // An incremental, non-final append happened mid-recording.
    expect(sent.length).toBeGreaterThanOrEqual(1);
    expect(sent[0].final).toBe(false);
    expect(sent[0].size).toBeGreaterThanOrEqual(ALIGN_BYTES);
  });
});

describe('O-07 · a halted stream can still be saved', () => {
  /**
   * The bound stops the recording; it must not make the held audio
   * unreachable. `halted` previously short-circuited every flush including the
   * final one, so tripping the bound left each mic's buffer in memory and its
   * GCS object open — while the operator was told the audio was "waiting to
   * upload".
   */
  it('flushes on finalise even after the bound halted every stream', async () => {
    const { transport, sent } = recordingTransport();
    stubSessionEndpoint();
    const onBoundReached = jest.fn();
    const chunks = [
      { blob: blobOf(1024), streamIndex: 0 },
      { blob: blobOf(LOCAL_BOUND_BYTES + 1), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
        onBoundReached,
      }),
    );

    expect(onBoundReached).toHaveBeenCalled();
    expect(result.current.status).toBe('stopped');

    await flushAll(result);

    // Both mics' audio reached GCS despite every stream being halted.
    expect(sent.some((s) => s.url.endsWith('stream-0'))).toBe(true);
    expect(sent.some((s) => s.url.endsWith('stream-1'))).toBe(true);
    expect(sent.every((s) => s.final)).toBe(true);
  });
});

describe('O-07 AC-4 · finalisation covers every stream', () => {
  it('closes each mic object, and one failing stream does not block the rest', async () => {
    const { transport, sent } = failingTransport('stream-1');
    stubSessionEndpoint();
    const chunks = [
      { blob: blobOf(1024), streamIndex: 0 },
      { blob: blobOf(1024), streamIndex: 1 },
    ];

    const chunksRef = { current: chunks };

    const { result } = renderHook(() =>
      useChunkUploader({
        recordingId: 'rec-1',
        chunksRef,
        chunkCount: chunks.length,
        recording: true,
        streams: [{ streamIndex: 0 }, { streamIndex: 1 }],
        transport,
      }),
    );

    await act(async () => {
      await result.current.finalise();
    });

    // allSettled, not all: stream 1's failure must not leave stream 0's
    // object open with its tail unwritten.
    expect(sent.some((s) => s.url.endsWith('stream-0'))).toBe(true);
  });
});
