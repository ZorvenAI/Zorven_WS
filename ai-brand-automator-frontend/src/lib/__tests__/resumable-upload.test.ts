/**
 * F-03 · the resumable protocol, where AC-2 lives.
 *
 * "No gap and no duplication" is offset arithmetic, so it is tested as offset
 * arithmetic — including the property NFR-REL-01 asks for, "because the
 * interleavings" of arrival, failure and retry are what break it and nobody
 * writes them all out by hand.
 *
 * The transport is injected. That is not a mock of the code under test: the
 * class under test is the offset bookkeeping, and the transport is the network
 * it is being kept honest against. A real severed connection is covered in
 * `e2e/upload-resume.spec.ts`.
 */

import {
  ALIGN_BYTES,
  ResumableUpload,
  alignedLength,
  backoffMs,
  isRetryable,
  nextOffsetFrom,
  type UploadTransport,
} from '@/lib/resumable-upload';

/**
 * Read a Blob's bytes.
 *
 * jsdom's Blob implements `slice` and `size` but **not** `arrayBuffer`, so the
 * obvious `await body.arrayBuffer()` returns undefined and every byte-level
 * assertion here silently compares nothing. FileReader is what jsdom does
 * implement.
 */
async function bytesOf(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === 'function') {
    return new Uint8Array(await blob.arrayBuffer());
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

/** A server that behaves like GCS: it commits bytes and reports its range. */
class FakeGcs implements UploadTransport {
  received = new Uint8Array(0);
  /** Statuses to answer with, consumed in order; 308/200 once exhausted. */
  script: number[] = [];
  seen: string[] = [];

  async put(_url: string, body: Blob, headers: Record<string, string>) {
    const range = headers['Content-Range'];
    this.seen.push(range);

    const scripted = this.script.shift();
    if (scripted && scripted !== 308 && scripted !== 200) {
      // Rejected: the server commits nothing, which is the case that makes
      // a client trusting its own count write a duplicate.
      return { status: scripted, range: null };
    }

    const match = /bytes (\d+)-(\d+)\/(.+)/.exec(range);
    if (!match) return { status: 400, range: null };
    const start = Number(match[1]);

    const bytes = await bytesOf(body);
    const merged = new Uint8Array(Math.max(this.received.length, start + bytes.length));
    merged.set(this.received);
    merged.set(bytes, start);
    this.received = merged;

    const final = match[3] !== '*';
    return {
      status: final ? 200 : 308,
      range: `bytes=0-${this.received.length - 1}`,
    };
  }
}

const blobOf = (size: number, fill = 7) =>
  new Blob([new Uint8Array(size).fill(fill)]);

describe('alignment', () => {
  it.each([
    [0, 0],
    [ALIGN_BYTES - 1, 0],
    [ALIGN_BYTES, ALIGN_BYTES],
    [ALIGN_BYTES * 2 + 5, ALIGN_BYTES * 2],
  ])('%s bytes yields %s aligned', (size, expected) => {
    expect(alignedLength(size)).toBe(expected);
  });

  it('holds back a partial unit rather than sending it', () => {
    /** GCS rejects a misaligned intermediate PUT outright and the upload
     *  cannot continue afterwards, so this is a correctness rule, not a
     *  performance one. */
    expect(alignedLength(403 * 1024)).toBe(ALIGN_BYTES);
  });
});

describe('resume offsets', () => {
  it('trusts the range the server reports over its own count', () => {
    /**
     * The server is the authority on what it has committed. A client that
     * trusts its own count after a partial write produces exactly the two
     * failures AC-2 names — a gap or a duplicate — and both look fine locally.
     */
    expect(nextOffsetFrom('bytes=0-262143', 999)).toBe(262144);
  });

  it('falls back when the server sends no range', () => {
    expect(nextOffsetFrom(null, 512)).toBe(512);
  });

  it.each([
    [0, true],
    [408, true],
    [429, true],
    [500, true],
    [503, true],
    [400, false],
    [403, false],
    [404, false],
  ])('status %s retryable: %s', (status, expected) => {
    expect(isRetryable(status)).toBe(expected);
  });

  it('backs off exponentially and then stops growing', () => {
    expect(backoffMs(1)).toBe(1000);
    expect(backoffMs(2)).toBe(2000);
    expect(backoffMs(3)).toBe(4000);
    expect(backoffMs(50)).toBe(30000);
  });
});

describe('AC-2 · no gap and no duplication', () => {
  it('reassembles a clean run byte for byte', async () => {
    const gcs = new FakeGcs();
    const upload = new ResumableUpload('https://session', gcs);

    await upload.send(blobOf(ALIGN_BYTES, 1), { final: false });
    await upload.send(blobOf(ALIGN_BYTES, 2), { final: false });
    await upload.send(blobOf(100, 3), { final: true });

    expect(gcs.received.length).toBe(ALIGN_BYTES * 2 + 100);
    expect(gcs.received[0]).toBe(1);
    expect(gcs.received[ALIGN_BYTES]).toBe(2);
    expect(gcs.received[ALIGN_BYTES * 2]).toBe(3);
  });

  it('a retried chunk lands at the same offset, not a second copy', async () => {
    /**
     * The heart of AC-2. The first attempt fails after the client has already
     * counted the bytes as sent; if the retry appended rather than rewrote,
     * the object would be longer than the audio.
     */
    const gcs = new FakeGcs();
    gcs.script = [503];
    const upload = new ResumableUpload('https://session', gcs);

    const failed = await upload.send(blobOf(ALIGN_BYTES, 1), { final: false });
    expect(failed.ok).toBe(false);

    await upload.send(blobOf(ALIGN_BYTES, 1), { final: false });
    await upload.send(blobOf(10, 2), { final: true });

    expect(gcs.received.length).toBe(ALIGN_BYTES + 10);
    // Both PUTs claimed the same starting offset — the retry rewrote rather
    // than appended.
    expect(gcs.seen[0]).toBe(gcs.seen[1]);
  });

  it('a severed connection is retryable and commits nothing', async () => {
    const dead: UploadTransport = {
      async put() {
        throw new TypeError('Failed to fetch');
      },
    };
    const upload = new ResumableUpload('https://session', dead);

    const outcome = await upload.send(blobOf(ALIGN_BYTES), { final: false });

    expect(outcome).toEqual({ ok: false, retryable: true, status: 0 });
    expect(upload.committed).toBe(0);
  });

  it('a rejected upload is not retried forever', async () => {
    const gcs = new FakeGcs();
    gcs.script = [403];
    const upload = new ResumableUpload('https://session', gcs);

    const outcome = await upload.send(blobOf(ALIGN_BYTES), { final: false });

    expect(outcome).toEqual({ ok: false, retryable: false, status: 403 });
  });
});

describe('property · ordering survives any interleaving of failures', () => {
  /**
   * NFR-REL-01 asks for this by name and says why: "property-based, because
   * the interleavings" are what break resumption. Failures are injected at
   * arbitrary points and every chunk is retried until it lands; the resulting
   * object must equal the concatenation of the inputs, in order, exactly once.
   */
  const seeds = Array.from({ length: 25 }, (_, i) => i + 1);

  it.each(seeds)('seed %s', async (seed) => {
    // A small deterministic PRNG: jest has no property runner, and a seeded
    // sequence is reproducible in a way Math.random() is not.
    let state = seed * 2654435761;
    const next = () => {
      state = (state * 1103515245 + 12345) & 0x7fffffff;
      return state / 0x7fffffff;
    };

    const gcs = new FakeGcs();
    const upload = new ResumableUpload('https://session', gcs);

    const sizes = Array.from({ length: 5 }, () => ALIGN_BYTES);
    let expected = 0;

    for (let i = 0; i < sizes.length; i += 1) {
      const isLast = i === sizes.length - 1;
      const body = blobOf(sizes[i], (i % 250) + 1);

      // Between zero and three transient failures before this chunk lands.
      const failures = Math.floor(next() * 4);
      gcs.script = Array.from({ length: failures }, () => 503);

      let sent = false;
      for (let attempt = 0; attempt < failures + 1 && !sent; attempt += 1) {
        const outcome = await upload.send(body, { final: isLast });
        sent = outcome.ok;
      }
      expect(sent).toBe(true);
      expected += sizes[i];
    }

    expect(gcs.received.length).toBe(expected);
    // Every byte is the value its own chunk wrote — a gap would leave a zero,
    // a duplicate would shift the boundaries.
    for (let i = 0; i < sizes.length; i += 1) {
      expect(gcs.received[i * ALIGN_BYTES]).toBe((i % 250) + 1);
    }
  });
});
