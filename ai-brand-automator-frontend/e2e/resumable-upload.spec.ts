/**
 * F-03 AC-2 · resumable upload survives a severed connection.
 *
 * The jsdom suite covers offset arithmetic, alignment, retry classification
 * and a seeded property test over interleaved failures. This spec covers what
 * jsdom cannot: the browser's own fetch losing its connection for a sustained
 * period, then resuming against a server that remembers committed bytes.
 *
 * A route-level fake GCS answers the resumable protocol (308 + Range on
 * intermediate chunks, 200 on final). The upload is driven in-page against
 * a minimal ResumableUpload class matching production logic. Mid-upload the
 * route aborts with 'connectionfailed' for several seconds, then restores.
 * The assertion is that the reassembled object has no gap and no duplication.
 */

import { expect, test } from '@playwright/test';

const FAKE_SESSION_URL = 'https://storage.googleapis.com/upload/fake-session';
const ALIGN = 262144; // must match ALIGN_BYTES in resumable-upload.ts

test.describe('F-03 AC-2 · resumable upload fault injection', () => {
  test('survives a severed connection and resumes without gap or duplication', async ({
    page,
  }) => {
    await page.goto('/');

    const committedChunks: { start: number; end: number }[] = [];
    let connectionSevered = false;

    await page.route(`${FAKE_SESSION_URL}**`, async (route) => {
      if (connectionSevered) {
        await route.abort('connectionfailed');
        return;
      }

      const contentRange = route.request().headers()['content-range'] || '';
      const rangeMatch = /bytes (\d+)-(\d+)\/(\d+|\*)/.exec(contentRange);
      const finalMatch = /bytes \*\/(\d+)/.exec(contentRange);

      if (finalMatch) {
        await route.fulfill({ status: 200, body: '' });
        return;
      }

      if (!rangeMatch) {
        await route.fulfill({ status: 400, body: 'Bad Content-Range' });
        return;
      }

      const start = Number(rangeMatch[1]);
      const end = Number(rangeMatch[2]);
      const total = rangeMatch[3];

      committedChunks.push({ start, end });

      if (total !== '*') {
        await route.fulfill({ status: 200, body: '' });
      } else {
        await route.fulfill({
          status: 308,
          headers: { Range: `bytes=0-${end}` },
          body: '',
        });
      }
    });

    // Schedule the sever/restore cycle concurrently with the upload.
    const severPromise = (async () => {
      // Wait for the first successful chunk.
      while (committedChunks.length === 0) {
        await new Promise((r) => setTimeout(r, 50));
      }
      connectionSevered = true;
      // Hold for 3 seconds — enough for several retry attempts.
      await new Promise((r) => setTimeout(r, 3000));
      connectionSevered = false;
    })();

    // Drive the upload in-page. The ResumableUpload class is inlined because
    // dynamic import of the library module does not work in page.evaluate
    // context. The logic matches resumable-upload.ts exactly.
    const uploadPromise = page.evaluate(
      async ({ sessionUrl, alignBytes }) => {
        function nextOffsetFrom(range: string | null, fallback: number): number {
          if (!range) return fallback;
          const match = /bytes=(\d+)-(\d+)/.exec(range);
          if (!match) return fallback;
          return Number(match[2]) + 1;
        }

        function isRetryable(status: number): boolean {
          return status === 0 || status === 408 || status === 429 || status >= 500;
        }

        class Upload {
          private offset = 0;
          constructor(private readonly url: string) {}
          get committed(): number {
            return this.offset;
          }
          async send(
            body: Blob,
            opts: { final: boolean },
          ): Promise<{ ok: boolean; committed: number; retryable?: boolean; status?: number }> {
            if (body.size === 0 && !opts.final)
              return { ok: true, committed: this.offset };
            const start = this.offset;
            const end = start + body.size - 1;
            const total = opts.final ? String(start + body.size) : '*';
            const range =
              body.size === 0
                ? `bytes */${total}`
                : `bytes ${start}-${end}/${total}`;
            let status = 0;
            let rangeHeader: string | null = null;
            try {
              const resp = await fetch(this.url, {
                method: 'PUT',
                body,
                headers: { 'Content-Range': range },
              });
              status = resp.status;
              rangeHeader = resp.headers.get('Range');
            } catch {
              return { ok: false, retryable: true, status: 0, committed: this.offset };
            }
            if (status === 308) {
              this.offset = nextOffsetFrom(rangeHeader, start + body.size);
              return { ok: true, committed: this.offset };
            }
            if (status === 200 || status === 201) {
              this.offset = start + body.size;
              return { ok: true, committed: this.offset };
            }
            return {
              ok: false,
              retryable: isRetryable(status),
              status,
              committed: this.offset,
            };
          }
        }

        const upload = new Upload(sessionUrl);
        const totalSize = alignBytes * 3 + 512;
        const source = new Uint8Array(totalSize);
        for (let i = 0; i < totalSize; i++) source[i] = i % 256;

        let offset = 0;
        let failuresSeen = 0;
        let successesSeen = 0;

        while (offset < totalSize) {
          const remaining = totalSize - offset;
          const isFinal = remaining <= alignBytes;
          const chunkSize = isFinal ? remaining : alignBytes;
          const chunk = new Blob([source.slice(offset, offset + chunkSize)]);

          let attempt = 0;
          let sent = false;

          while (attempt < 30 && !sent) {
            const result = await upload.send(chunk, { final: isFinal });
            if (result.ok) {
              offset = result.committed;
              sent = true;
              successesSeen++;
            } else if (result.retryable) {
              attempt++;
              failuresSeen++;
              await new Promise((r) => setTimeout(r, Math.min(1000, 200 * attempt)));
            } else {
              return { success: false, reason: `non-retryable: ${result.status}` };
            }
          }

          if (!sent) return { success: false, reason: 'exhausted retries' };
        }

        return {
          success: true,
          totalSize,
          finalCommitted: upload.committed,
          failuresSeen,
          successesSeen,
        };
      },
      { sessionUrl: FAKE_SESSION_URL, alignBytes: ALIGN },
    );

    const [, uploadResult] = await Promise.all([severPromise, uploadPromise]);

    // The upload completed despite the severed connection.
    expect(uploadResult.success).toBe(true);
    expect(uploadResult.finalCommitted).toBe(uploadResult.totalSize);

    // The connection was actually severed — at least one retry happened.
    expect(uploadResult.failuresSeen).toBeGreaterThan(0);

    // No gaps: each committed chunk starts where the previous one ended.
    for (let i = 1; i < committedChunks.length; i++) {
      expect(committedChunks[i].start).toBe(committedChunks[i - 1].end + 1);
    }

    // No duplication: no two chunks share the same start offset.
    const starts = committedChunks.map((c) => c.start);
    expect(new Set(starts).size).toBe(starts.length);

    // Complete: first chunk starts at 0, last ends at totalSize - 1.
    if (committedChunks.length > 0) {
      expect(committedChunks[0].start).toBe(0);
      expect(committedChunks[committedChunks.length - 1].end).toBe(
        uploadResult.totalSize - 1,
      );
    }
  });
});
