import { defineConfig, devices } from '@playwright/test';

/**
 * Browser tests, for claims jsdom cannot make.
 *
 * Added by E-02. Its AC-2 is a layout claim — a 13-inch screen, twenty
 * questions, no horizontal scrolling, question text not truncated to a single
 * line — and jsdom has no layout engine: every element reports zero width and
 * height. A jsdom test could only assert that I wrote the CSS classes I meant
 * to write, which is the implementation reading itself back.
 *
 * `e2e/file-browser.spec.ts` is deliberately excluded. It predates this config
 * and has never run — its own header says "npm install -D @playwright/test",
 * which had not been done — and it needs a logged-in user against a seeded
 * backend. Reviving it is real work and belongs to whoever owns that feature,
 * not to a layout story that happened to install the runner.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: ['**/meeting-view.spec.ts'],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'laptop-13in',
      use: {
        ...devices['Desktop Chrome'],
        // AC-2's "real laptop". 1280×800 is the 13-inch MacBook's default
        // logical resolution, and the browser chrome eats the rest — which is
        // the point of naming a size rather than testing at 1920 and calling
        // it responsive.
        viewport: { width: 1280, height: 800 },
      },
    },
  ],

  // `next dev`, not `next build && next start`.
  //
  // This project sets `output: "standalone"` for the Docker image, and Next
  // warns that `next start` "does not work" with it — it served pages here,
  // but unreliably: a stale instance answered 404 for routes that were in the
  // build. Depending on behaviour the framework disclaims is how a layout
  // suite starts failing for reasons that have nothing to do with layout.
  //
  // The alternative would be running the standalone server, which needs its
  // static assets copied into place by hand. Dev mode emits the same Tailwind
  // utilities, so the geometry under test is the same.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
  },
});
