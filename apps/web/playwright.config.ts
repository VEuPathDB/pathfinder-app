import { defineConfig, devices } from "@playwright/test";

import type { SiteOption } from "./e2e/fixtures/test";

const isCI = Boolean(process.env["CI"]);

/** The sites the turn-driving specs run on, from `E2E_SITES` (comma separated). */
const turnSites = (process.env["E2E_SITES"] ?? "plasmodb")
  .split(",")
  .map((site) => site.trim())
  .filter((site) => site !== "");

/** A test that sends an arc token; its outcome depends on the site's data. */
const TURN_TAG = /@turn\b/;
/** A test whose subject is a named site; it runs once, whatever `E2E_SITES` holds. */
const NAMED_SITE_TAG = /@named-site\b/;

/**
 * Playwright E2E test configuration.
 *
 * ## Running locally
 *
 * 1. Start Docker services with the test overlays. The e2e overlay builds the
 *    web container's `runner` target, so port 3000 serves the production
 *    build: no dev overlay portal over the controls a spec clicks, and no
 *    per-route compile to grow the server's heap.
 *
 *      docker compose --env-file .env.test \
 *        -f docker-compose.yml \
 *        -f docker-compose.dev.yml \
 *        -f docker-compose.e2e.yml \
 *        up -d --build --wait api worker web
 *
 * 2. Export the registered VEuPathDB account and run the tests. Either the
 *    token itself, or the email and password, which global setup signs in
 *    with once and exports as the token:
 *
 *      export WDK_TEST_TOKEN=...   # from .env.dev; never printed or committed
 *      yarn test:e2e
 *
 *    `E2E_SITES=plasmodb,vectorbase yarn test:e2e` runs every `@turn` test once
 *    per site; the UI-only and `@named-site` tests run once either way.
 *
 * ## CI
 *
 * The GitHub Actions workflow starts both servers, sets PLAYWRIGHT_BASE_URL,
 * and passes the WDK_TEST_EMAIL and WDK_TEST_PASSWORD repository secrets.
 *
 * ## Authentication
 *
 * VEuPathDB refuses guest service calls, so every worker acts as the registered
 * account: `e2e/fixtures/test.ts` puts `WDK_TEST_TOKEN` in the `Authorization`
 * cookie of the per-worker storage state (`e2e/.auth/worker-{N}.json`), which is
 * the token the API forwards to WDK. PathFinder identity stays per worker via
 * `/dev/login?user_id=worker-{N}`, so parallel workers never share gene sets,
 * strategies, or conversations: `clearAllGeneSets` only affects the calling
 * worker's user. The postcondition client in `e2e/fixtures/api-client.ts` copies
 * the whole browser cookie jar, so it carries both cookies too.
 */
export default defineConfig<SiteOption>({
  testDir: "./e2e",
  // Waits for the web container to accept connections, then renders each route
  // pattern once so the first spec to enter one does not pay the cold render
  // inside its own budget.
  globalSetup: "./e2e/global-setup.ts",
  timeout: isCI ? 120_000 : 60_000,
  expect: { timeout: 15_000 },
  retries: isCI ? 1 : 0,
  forbidOnly: isCI,
  fullyParallel: true,
  workers: 2,

  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "on-failure" }]],

  use: {
    baseURL: process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000",
    trace: isCI ? "on-first-retry" : "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },

  // One `turns@<site>` project per site in `E2E_SITES`, so a merged report
  // keeps both sites apart; the UI-only specs and the named-site specs run once.
  projects: [
    ...turnSites.map((siteId) => ({
      name: `turns@${siteId}`,
      grep: TURN_TAG,
      grepInvert: NAMED_SITE_TAG,
      timeout: 300_000,
      use: { siteId },
    })),
    {
      name: "feature@plasmodb",
      grepInvert: [TURN_TAG, NAMED_SITE_TAG],
      timeout: 120_000,
      use: { siteId: "plasmodb" },
    },
    {
      name: "sites",
      grep: NAMED_SITE_TAG,
      timeout: 300_000,
      use: { siteId: "plasmodb" },
    },
  ],

  // No webServer: both local and CI drive containers the recipe above starts.
  // Port 3000 serves the production build of the `runner` target, and the API
  // on port 8000 runs with PATHFINDER_CHAT_PROVIDER=mock from the e2e overlay.
});
