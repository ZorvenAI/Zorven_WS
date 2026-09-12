/**
 * F-02 · what only a real browser can settle.
 *
 * The jsdom suite substitutes MediaRecorder, getUserMedia and AudioContext,
 * which is right for state-machine behaviour but cannot answer AC-2: whether
 * Chromium *actually* produces opus, and whether `ondataavailable` really
 * fires on the timeslice we asked for. A jsdom assertion there would confirm
 * only that I passed the arguments I meant to pass.
 *
 * Chromium is launched with `--use-fake-device-for-media-stream`, which feeds
 * a synthetic tone through the real capture pipeline: a genuine MediaRecorder
 * encoding genuine audio. Permission is granted and denied through Playwright's
 * own context API, so a denial arrives as the browser's own NotAllowedError
 * rather than one the test invented.
 *
 * Driven against the hook in the page rather than through the meeting UI: the
 * meeting route needs consent, a session and a questionnaire, and none of that
 * has anything to do with whether opus comes out of the encoder.
 */

import { expect, test } from '@playwright/test';

interface RecordingReport {
  supported: boolean;
  mimeType?: string;
  sampleRate?: number;
  chunks?: number;
  totalBytes?: number;
  medianGap?: number | null;
  elapsed?: number;
}

/**
 * Runs the hook's configuration inside the page and reports what happened.
 *
 * An inline callback, not a string built with `new Function`: Playwright
 * serialises the function's own source to the page, and a function object
 * constructed in the test process serialises to nothing — which is how the
 * first version of this spec got `undefined` back from every call.
 */
async function record(
  page: import('@playwright/test').Page,
  { mimeTypes, timeslice, ms }: { mimeTypes: string[]; timeslice: number; ms: number },
): Promise<RecordingReport> {
  return page.evaluate(
    async ({ mimeTypes, timeslice, ms }) => {
      const type = mimeTypes.find((t) => MediaRecorder.isTypeSupported(t)) || null;
      if (!type) return { supported: false } as RecordingReport;

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 48000, channelCount: 1 },
      });
      const context = new AudioContext({ sampleRate: 48000 });
      if (context.state === 'suspended') await context.resume();
      const startedAt = context.currentTime;

      const recorder = new MediaRecorder(stream, { mimeType: type });
      const arrivals: number[] = [];
      const sizes: number[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size) {
          arrivals.push(performance.now());
          sizes.push(event.data.size);
        }
      };
      recorder.start(timeslice);
      await new Promise((resolve) => setTimeout(resolve, ms));
      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });

      const elapsed = context.currentTime - startedAt;
      stream.getTracks().forEach((t) => t.stop());
      await context.close();

      const gaps = arrivals.slice(1).map((at, i) => at - arrivals[i]);
      gaps.sort((a, b) => a - b);
      return {
        supported: true,
        mimeType: type,
        sampleRate: context.sampleRate,
        chunks: sizes.length,
        totalBytes: sizes.reduce((a, b) => a + b, 0),
        medianGap: gaps[Math.floor(gaps.length / 2)] ?? null,
        elapsed,
      } as RecordingReport;
    },
    { mimeTypes, timeslice, ms },
  );
}

const OPUS = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus'];

test.describe('AC-2 · the format the pipeline expects, in a real browser', () => {
  test.use({ permissions: ['microphone'] });

  test('produces opus at 48 kHz on the cadence we asked for', async ({ page }) => {
    await page.goto('/');

    const result = await record(page, { mimeTypes: OPUS, timeslice: 20, ms: 800 });

    expect(result.supported, 'Chromium should support an opus container').toBe(true);
    expect(result.mimeType).toContain('codecs=opus');
    expect(result.sampleRate).toBe(48000);

    // Real audio came out, not an empty stream. A fake device that produced
    // nothing would still satisfy every other assertion here.
    expect(result.totalBytes).toBeGreaterThan(0);

    // The cadence F-03 depends on. Bounded loosely rather than pinned to 20 ms:
    // the browser coalesces under load and a CI runner is exactly that. The
    // claim under test is "small and regular", not "exactly 20" — the failure
    // this guards against is the *default*, which delivers one blob at stop.
    expect(result.chunks).toBeGreaterThan(5);
    expect(result.medianGap).toBeLessThan(200);
  });

  test('the audio clock tracks the recording, not the wall clock', async ({
    page,
  }) => {
    /**
     * FR-REC-02 wants duration error under a second over 45 minutes. That
     * fixture is not run here and is not run anywhere — a 45-minute test is a
     * test nobody executes. What is checked is the property the guarantee
     * rests on: elapsed comes from AudioContext.currentTime, which advances
     * with the audio hardware. Over 800 ms it should agree closely; the
     * 45-minute figure remains unverified and the PR says so.
     */
    await page.goto('/');

    const result = await record(page, { mimeTypes: OPUS, timeslice: 20, ms: 800 });

    expect(result.elapsed).toBeGreaterThan(0.6);
    expect(result.elapsed).toBeLessThan(1.4);
  });
});

test.describe('AC-1 · a denied microphone', () => {
  test('surfaces as NotAllowedError from the browser itself', async ({
    page,
    context,
  }) => {
    /**
     * The denial the hook's `catch` has to handle. jsdom can only throw an
     * error the test constructed; this is Chromium refusing, which is what
     * decides whether the branch is reachable at all.
     */
    await context.clearPermissions();
    await page.goto('/');

    const failure = await page.evaluate(async () => {
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        return { threw: false, name: null };
      } catch (error) {
        return { threw: true, name: (error as Error).name };
      }
    });

    expect(failure.threw).toBe(true);
    expect(failure.name).toBe('NotAllowedError');
  });
});
