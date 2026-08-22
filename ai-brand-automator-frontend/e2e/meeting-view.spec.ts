/**
 * E-02 AC-2 · "The layout survives a real laptop".
 *
 * The one criterion in this story that jsdom cannot speak to. It is entirely
 * about rendered geometry: at a 13-inch viewport, with twenty questions and a
 * running feedback stream, all three regions stay usable, nothing scrolls
 * sideways, and question text is not squashed onto one line. jsdom reports
 * every element as zero by zero, so the only jsdom version of this test would
 * assert that the CSS classes I wrote are the CSS classes I wrote.
 *
 * The questionnaire is served by `page.route` rather than by Django. The
 * subject under test is the layout: a real browser laying out the real
 * component with the real stylesheet. Standing up Postgres, a tenant, a
 * session and an approved questionnaire would not make the geometry any more
 * real, and it would make a layout test fail for reasons that have nothing to
 * do with layout. What must not be faked here — the browser and the CSS —
 * is not.
 */

import { expect, test, type Page } from '@playwright/test';

const SESSION_ID = 'e2e-session';
const MEETING_URL = `/onboarding/sessions/${SESSION_ID}/meeting`;

/** Long enough to need wrapping at this width, which is the case AC-2 names. */
const QUESTIONS = Array.from({ length: 20 }, (_, i) => ({
  id: `q-${i + 1}`,
  text:
    `Question ${i + 1}: what made you decide to roast in small batches rather ` +
    `than scale the way the rest of the market did, and who told you it would ` +
    `not work?`,
  workflow_target: ['WF1', 'WF2', 'WF3'][i % 3],
  status: 'PENDING',
  order: i + 1,
}));

/**
 * One question with a genuinely unbreakable run of characters.
 *
 * Two attempts were needed and the first was wrong, which is worth recording.
 * Ordinary prose wraps on its own, so it can prove nothing about width. A URL
 * looks unbreakable and is not — browsers take line breaks after `/`, `?` and
 * `&`. Only an unbroken run has no break opportunity at all, and operators do
 * paste those: a reference code, an order id, an API key.
 *
 * Without this question the whole suite stayed green while the checklist pane
 * scrolled sideways by 665px.
 */
QUESTIONS[7].text = `Which system is this reference from? ${'X7QLMBTZ'.repeat(20)}`;

async function openMeeting(page: Page) {
  await page.addInitScript(() => {
    // useAuth() only checks for a token's presence before rendering.
    window.localStorage.setItem('access_token', 'e2e-token');
    window.localStorage.setItem('refresh_token', 'e2e-refresh');
  });

  // Every API call, not only the questionnaire. The page also resolves tenant
  // context on mount, and a 401 from *any* of them makes the api client clear
  // the token and bounce to /auth/login — which is how the first version of
  // this spec ended up asserting the layout of the login page.
  await page.route('**/api/v1/**', async (route) => {
    const url = route.request().url();
    // A bare array for everything else. Tenant context calls `.find` on its
    // response, so an object shaped like a paginated page throws inside the
    // provider and the error boundary swallows the whole page.
    const body: unknown =
      url.includes('/questionnaires/')
        ? [{ id: 'qn-1', version: 3, questions: QUESTIONS }]
        : [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  await page.goto(MEETING_URL);
  await expect(page.getByRole('region', { name: /prepared questions/i })).toBeVisible();
}

test.describe('AC-2 · the layout survives a real laptop', () => {
  test('nothing scrolls sideways at 1280×800 with twenty questions', async ({
    page,
  }) => {
    await openMeeting(page);

    const overflow = await page.evaluate(() => {
      const measure = (node: Element | null) =>
        node ? { sw: node.scrollWidth, cw: node.clientWidth } : null;
      return {
        document: measure(document.documentElement),
        // Each region as well as the page. This is the correction that made
        // the test real: the document stayed exactly 1280 wide while the
        // checklist pane scrolled sideways by 665px, because the overflow was
        // *inside* a region rather than on the page. AC-2 says the regions
        // remain usable without horizontal scrolling, and only a per-region
        // measurement can tell.
        checklist: measure(document.querySelector('[data-testid="checklist-pane"]')),
        feedback: measure(document.querySelector('[data-testid="feedback-scroller"]')),
        rail: measure(document.querySelector('[data-testid="rail-scroller"]')),
      };
    });

    for (const [name, box] of Object.entries(overflow)) {
      expect(box, `${name} was not found`).not.toBeNull();
      // A single pixel is the symptom of a child that refused to shrink — a
      // missing min-w-0, or text with no break opportunity. Worth failing on
      // exactly, because it never gets better on its own.
      expect(box!.sw, `${name} scrolls horizontally`).toBeLessThanOrEqual(box!.cw);
    }
  });

  test('the page itself does not scroll, so the panes are what move', async ({
    page,
  }) => {
    /**
     * AC-1's precondition. Three independently scrolling regions are only
     * independent while the document does not scroll — an outer scrollbar
     * moves all three together and the panes become decorative.
     *
     * This failed by 28px when it was first written: the back link sat above
     * the fixed-height view rather than inside its header, so the box started
     * 28px lower while still being sized `100vh - 4rem`. Small enough to look
     * like nothing and to break the criterion completely.
     */
    await openMeeting(page);

    const vertical = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
    }));

    expect(vertical.scrollHeight).toBeLessThanOrEqual(vertical.clientHeight);
  });

  test('question text wraps instead of being truncated to one line', async ({
    page,
  }) => {
    await openMeeting(page);

    const question = page.getByText(/what made you decide to roast/).first();
    const box = await question.boundingBox();
    const lineHeight = await question.evaluate(
      (node) => parseFloat(getComputedStyle(node).lineHeight) || 20,
    );

    expect(box).not.toBeNull();
    // More than one line high is the observable form of "not truncated". The
    // alternative check — that no `truncate` class is present — passes just as
    // happily when a parent clips the text instead.
    expect(box!.height).toBeGreaterThan(lineHeight * 1.5);
  });

  test('all three regions are visible and none is squeezed away', async ({
    page,
  }) => {
    await openMeeting(page);

    const regions = {
      questions: page.getByRole('region', { name: /prepared questions/i }),
      feedback: page.getByRole('region', { name: /agent feedback/i }),
      rail: page.getByRole('complementary', { name: /recordings and captures/i }),
    };

    for (const [name, locator] of Object.entries(regions)) {
      await expect(locator, `${name} region`).toBeVisible();
      const box = await locator.boundingBox();
      // "Usable" has to mean something measurable. A region collapsed to a
      // sliver is technically visible and of no use to anybody.
      expect(box!.width, `${name} width`).toBeGreaterThan(180);
      expect(box!.height, `${name} height`).toBeGreaterThan(80);
    }
  });

  test('the panes scroll independently of one another', async ({ page }) => {
    /**
     * AC-1's real form, which only a browser can show: scrolling the checklist
     * must leave the feedback pane and the rail exactly where they were.
     */
    await openMeeting(page);

    const checklist = page.getByTestId('checklist-pane');
    const feedback = page.getByTestId('feedback-scroller');

    const before = await feedback.evaluate((node) => node.scrollTop);
    await checklist.evaluate((node) => {
      node.scrollTop = 200;
    });

    expect(await checklist.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);
    expect(await feedback.evaluate((node) => node.scrollTop)).toBe(before);
    // And the page itself never scrolled, which is what makes the panes the
    // things that move.
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
});
