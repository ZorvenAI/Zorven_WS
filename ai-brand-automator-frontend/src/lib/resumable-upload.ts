/**
 * The GCS resumable upload protocol, as much of it as F-03 needs.
 *
 * Pure functions and one class with an injectable transport, deliberately
 * separate from React: the ordering and offset arithmetic is the part AC-2
 * turns on, and it should be testable without mounting anything.
 *
 * **Resumable, not composed.** A resumable session is addressed by byte
 * offset, so a chunk retried after a network drop lands at the same offset
 * rather than appending a second copy. That is AC-2's "no duplication" for
 * free; composing many small objects would make it something you have to
 * solve.
 */

/**
 * GCS requires every chunk except the last to be a multiple of 256 KiB.
 *
 * This is not a tuning knob — a non-aligned intermediate PUT is rejected, and
 * the upload cannot continue. Measured against Chromium's opus output at
 * ~13.7 KB/s, one unit is about 19 seconds of audio, so AC-1's thirty-second
 * cadence produces roughly 403 KiB and clears the floor comfortably. The
 * remainder above a whole number of units is carried forward rather than sent.
 */
export const ALIGN_BYTES = 262144;

export type UploadOutcome =
  | { ok: true; committed: number }
  | { ok: false; retryable: boolean; status: number };

export interface UploadTransport {
  put(
    url: string,
    body: Blob,
    headers: Record<string, string>,
  ): Promise<{ status: number; range: string | null }>;
}

/** The browser's fetch, which is what production uses. */
export const fetchTransport: UploadTransport = {
  async put(url, body, headers) {
    const response = await fetch(url, { method: 'PUT', body, headers });
    return { status: response.status, range: response.headers.get('Range') };
  },
};

/**
 * How many whole aligned units are available in `size` bytes.
 *
 * Zero means "not enough yet, keep buffering", which is the common answer
 * early in a recording and is why the caller must tolerate a flush that sends
 * nothing.
 */
export function alignedLength(size: number): number {
  return Math.floor(size / ALIGN_BYTES) * ALIGN_BYTES;
}

/**
 * `Range: bytes=0-262143` → 262144, the next offset to send from.
 *
 * GCS answers 308 with the range it has actually committed, which is the
 * authority on where to resume. Trusting our own count instead is how a
 * retry writes the same bytes twice or skips a gap — the two failures AC-2
 * names, both of which look fine locally.
 */
export function nextOffsetFrom(range: string | null, fallback: number): number {
  if (!range) return fallback;
  const match = /bytes=(\d+)-(\d+)/.exec(range);
  if (!match) return fallback;
  return Number(match[2]) + 1;
}

export function isRetryable(status: number): boolean {
  // 408, 429 and 5xx are the transient set; a 0 comes from fetch failing
  // outright, which is the severed-connection case AC-2 is about.
  return status === 0 || status === 408 || status === 429 || status >= 500;
}

/**
 * Uploads a growing byte stream to one resumable session.
 *
 * Owns the offset and nothing else — no timers, no React state, no knowledge
 * of where the bytes came from. The hook drives it.
 */
export class ResumableUpload {
  private offset = 0;

  constructor(
    private readonly sessionUrl: string,
    private readonly transport: UploadTransport = fetchTransport,
  ) {}

  get committed(): number {
    return this.offset;
  }

  /**
   * Send one aligned run of bytes.
   *
   * `final` sends the total size in the Content-Range, which is what tells
   * GCS the object is complete; until then the total is `*` because a
   * recording in progress does not know its own length.
   */
  async send(body: Blob, { final }: { final: boolean }): Promise<UploadOutcome> {
    if (body.size === 0 && !final) return { ok: true, committed: this.offset };

    const start = this.offset;
    const end = start + body.size - 1;
    const total = final ? String(start + body.size) : '*';
    const range =
      body.size === 0 ? `bytes */${total}` : `bytes ${start}-${end}/${total}`;

    let status = 0;
    let rangeHeader: string | null = null;
    try {
      const response = await this.transport.put(this.sessionUrl, body, {
        'Content-Range': range,
      });
      status = response.status;
      rangeHeader = response.range;
    } catch {
      // fetch rejects on a severed connection rather than returning a status.
      return { ok: false, retryable: true, status: 0 };
    }

    // 308 is "resume incomplete" — the success case for every chunk but the
    // last. 200/201 close the object.
    if (status === 308) {
      this.offset = nextOffsetFrom(rangeHeader, start + body.size);
      return { ok: true, committed: this.offset };
    }
    if (status === 200 || status === 201) {
      this.offset = start + body.size;
      return { ok: true, committed: this.offset };
    }

    return { ok: false, retryable: isRetryable(status), status };
  }
}

/** Exponential, capped. A recording that outlasts an outage still retries. */
export function backoffMs(attempt: number, base = 1000, cap = 30000): number {
  return Math.min(cap, base * 2 ** Math.max(0, attempt - 1));
}
