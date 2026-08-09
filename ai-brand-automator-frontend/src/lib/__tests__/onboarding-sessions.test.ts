/**
 * E-01 · NFR-COMPAT and the wizard deep link.
 *
 * The card puts NFR-COMPAT's assertion in `tests/e2e/test_process_to_review.py`
 * "from this story onward". That file does not exist, and it is a Python e2e
 * suite while this is a Next.js route — there is no browser-level e2e tooling
 * in this repo to put it in. Rather than claim an e2e I cannot run, the
 * guarantee is asserted here at the level the repo actually supports, and the
 * gap is stated in the PR.
 *
 * What is checked: the wizard routes still exist as their own pages, and the
 * deep link into page 1 carries what K-01 needs to send an operator back.
 */

import fs from 'node:fs';
import path from 'node:path';

import { apiClient } from '@/lib/api';
import {
  listRecordings,
  listSessions,
  wizardDeepLink,
} from '@/lib/onboarding-sessions';

jest.mock('@/lib/api', () => ({ apiClient: { get: jest.fn() } }));

const mockedGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;

function responseOf(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

const APP = path.join(process.cwd(), 'src', 'app', 'onboarding');

describe('NFR-COMPAT · the manual wizard survives', () => {
  it.each(['step-1', 'step-2', 'step-3', 'step-4', 'step-5'])(
    'keeps %s as its own route',
    (step) => {
      /**
       * E-01 replaced /onboarding — previously a redirect into step 1 — with
       * a landing view. The wizard pages are separate routes and must be
       * untouched by that: AC-2 requires an existing bookmark to keep working
       * "with no meeting required at any point".
       */
      expect(fs.existsSync(path.join(APP, step, 'page.tsx'))).toBe(true);
    },
  );

  it('no longer redirects away from /onboarding', () => {
    /**
     * The behaviour E-01 changes, asserted so a future refactor cannot
     * quietly restore it. The old page pushed editors to step-1 and viewers
     * to /chat, which is why a Viewer could not reach onboarding at all.
     */
    const source = fs.readFileSync(path.join(APP, 'page.tsx'), 'utf8');

    expect(source).not.toMatch(/router\.push/);
    expect(source).toContain('OnboardingHome');
  });
});

describe('wizardDeepLink', () => {
  it('carries the company and session so K-01 can return the operator', () => {
    const link = wizardDeepLink({ id: 'sess-1', company: 'company-1' });

    expect(link).toContain('/onboarding/step-1?');
    expect(link).toContain('companyId=company-1');
    expect(link).toContain('sessionId=sess-1');
  });

  it('falls back to the bare wizard when there is no session', () => {
    /**
     * The manual path has to work for someone who has never held a meeting —
     * that is the whole of NFR-COMPAT. A link that required a session id
     * would break exactly that person.
     */
    expect(wizardDeepLink(null)).toBe('/onboarding/step-1');
    expect(wizardDeepLink(undefined)).toBe('/onboarding/step-1');
  });

  it('omits the company when a session has none', () => {
    const link = wizardDeepLink({ id: 'sess-2', company: null });

    expect(link).toContain('sessionId=sess-2');
    expect(link).not.toContain('companyId');
  });
});


describe('the list clients actually read the response', () => {
  /**
   * These exist because review found two bugs that made every call return an
   * empty list, and nothing caught them: the component tests mocked
   * `listSessions` and `listRecordings` themselves, which is to say they
   * mocked the two functions that contained the bugs.
   *
   * Mocking `apiClient` instead leaves the code under test in the path.
   */
  beforeEach(() => jest.clearAllMocks());

  it('parses the body rather than returning the Response', async () => {
    // apiClient.get resolves to a Response. Passing it straight to a parser
    // that expects a body matched nothing and yielded [] on every call.
    mockedGet.mockResolvedValue(responseOf([{ id: 'sess-1' }]));

    await expect(listSessions()).resolves.toHaveLength(1);
  });

  it('unwraps a paginated body too', async () => {
    mockedGet.mockResolvedValue(responseOf({ count: 1, results: [{ id: 'sess-1' }] }));

    await expect(listSessions()).resolves.toHaveLength(1);
  });

  it('does not double-prefix the api version', async () => {
    // env.getApiUrl already prepends /api/v1, so a full path produced
    // /api/v1/api/v1/onboarding/... — a 404 that surfaced as an empty list.
    mockedGet.mockResolvedValue(responseOf([]));

    await listSessions();
    await listRecordings();

    for (const [path] of mockedGet.mock.calls) {
      expect(path).not.toContain('/api/v1');
      expect(path).toMatch(/^\/onboarding\//);
    }
  });

  it('throws on a non-ok response instead of reporting no sessions', async () => {
    // A 500 that returns [] is indistinguishable from a tenant with none.
    mockedGet.mockResolvedValue(responseOf({ detail: 'boom' }, false, 500));

    await expect(listSessions()).rejects.toThrow('API 500');
  });
});
