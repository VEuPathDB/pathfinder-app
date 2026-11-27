import { defineConfig, devices } from "@playwright/test";

import type { SiteOption } from "./e2e/fixtures/test";
import { readManifest, wireMode } from "./e2e/fixtures/wire";
import { stalenessLines } from "./e2e/fixtures/wire-recordings";
import { BASE_PATH } from "./src/lib/basePath";

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

/** Workers per mode: a record run is serial, a CI shard runs two, a local run four. */
const WORKERS = wireMode() === "record" ? 1 : isCI ? 2 : 4;

/**
 * Playwright E2E test configuration.
 *
 * ## Replay (every run on the Mac and in CI)
 *
 * The stack reaches VEuPathDB only through the wdk-wire proxy, which answers
 * from the recordings in `e2e/wire/` and refuses any request it holds no
 * recording for with a 418 (docs/knowledge/decisions/e2e-replays-recorded-wdk.md).
 * Each test signs its own token with the key wdk-wire made at start, so each
 * test is its own Strategist user, and no VEuPathDB account is needed:
 *
 *      scripts/e2e-wire.sh replay
 *
 * A test fails when the app sent a request the recording does not hold, or
 * did not send a write the recording holds.
 *
 * ## Record and refresh (cedar only, by hand)
 *
 * `scripts/e2e-wire.sh record --test <spec:line>` records the named tests
 * against QA with one worker, as the registered account (`WDK_TEST_EMAIL` and
 * `WDK_TEST_PASSWORD` in the shell). `scripts/e2e-wire.sh refresh` re-sends
 * every recording to QA and writes a drift report.
 *
 * `E2E_SITES=plasmodb,vectorbase` runs every `@turn` test once per site; the
 * UI-only and `@named-site` tests run once either way.
 */
export default defineConfig<SiteOption>({
  testDir: "./e2e",
  // Waits for the web container to accept connections, then renders each route
  // pattern once so the first spec to enter one does not pay the cold render
  // inside its own budget.
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  metadata: { wdkReplay: stalenessLines(readManifest(), new Date()).join("\n") },
  timeout: 180_000,
  expect: { timeout: 15_000 },
  retries: isCI ? 1 : 0,
  forbidOnly: isCI,
  fullyParallel: true,
  workers: WORKERS,

  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "on-failure" }]],

  use: {
    // A relative path resolves under the base path only when the base ends in "/".
    baseURL: `${process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000"}${BASE_PATH}/`,
    trace: isCI
      ? "on-first-retry"
      : {
          mode: "retain-on-failure",
          screenshots: false,
          snapshots: true,
          sources: false,
        },
    screenshot: "only-on-failure",
    video: isCI ? "retain-on-failure" : "off",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    ...devices["Desktop Chrome"],
    viewport: { width: 1680, height: 900 },
  },

  // One `turns@<site>` project per site in `E2E_SITES`, so a merged report
  // keeps both sites apart; the UI-only specs and the named-site specs run once.
  projects: [
    ...turnSites.map((siteId) => ({
      name: `turns@${siteId}`,
      grep: TURN_TAG,
      grepInvert: NAMED_SITE_TAG,
      use: { siteId },
    })),
    {
      name: "feature@plasmodb",
      grepInvert: [TURN_TAG, NAMED_SITE_TAG],
      use: { siteId: "plasmodb" },
    },
    {
      name: "sites",
      grep: NAMED_SITE_TAG,
      use: { siteId: "plasmodb" },
    },
  ],

  // No webServer: both local and CI drive containers scripts/e2e-wire.sh starts.
});
