import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env["CI"]);

// Feature specs that send a message through the mock provider and wait on a
// turn. Their data-part waits starve when every worker slot holds a turn, so
// they run in the serialized `feature-turns` project instead of `feature`.
const turnDrivingFeatureSpecs = [
  "**/e2e/feature/ai-workbench-integration.spec.ts",
  "**/e2e/feature/auth.spec.ts",
  "**/e2e/feature/auto-build.spec.ts",
  "**/e2e/feature/branch-switch.spec.ts",
  "**/e2e/feature/chat.spec.ts",
  "**/e2e/feature/conversations.spec.ts",
  "**/e2e/feature/dependent-strategy.spec.ts",
  "**/e2e/feature/dismissed-strategies.spec.ts",
  "**/e2e/feature/execution-phase.spec.ts",
  "**/e2e/feature/experiment-flows.spec.ts",
  "**/e2e/feature/fork-branch.spec.ts",
  "**/e2e/feature/insert-saved.spec.ts",
  "**/e2e/feature/strategy-complex-edit.spec.ts",
  "**/e2e/feature/strategy-duplicate-rename.spec.ts",
  "**/e2e/feature/strategy-graph.spec.ts",
  "**/e2e/feature/strategy-operator-persistence.spec.ts",
  "**/e2e/feature/strategy-overhaul.spec.ts",
  "**/e2e/feature/strategy-param-edit.spec.ts",
  "**/e2e/feature/thread-surgery/*.spec.ts",
  "**/e2e/feature/usage-reconciliation.spec.ts",
  "**/e2e/feature/user-data.spec.ts",
];

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
export default defineConfig({
  testDir: "./e2e",
  // Waits for the web container to accept connections, then renders each route
  // pattern once so the first spec to enter one does not pay the cold render
  // inside its own budget.
  globalSetup: "./e2e/global-setup.ts",
  timeout: isCI ? 120_000 : 60_000,
  expect: { timeout: 15_000 },
  retries: isCI ? 2 : 0,
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

  projects: [
    {
      name: "feature",
      testDir: "./e2e/feature",
      testIgnore: turnDrivingFeatureSpecs,
      timeout: 120_000,
    },
    {
      name: "feature-turns",
      testDir: "./e2e/feature",
      testMatch: turnDrivingFeatureSpecs,
      timeout: 120_000,
      fullyParallel: false,
    },
    {
      name: "cross-feature",
      testDir: "./e2e/cross-feature",
      timeout: 120_000,
      // All cross-feature tests run enrichment against live VEuPathDB WDK
      // APIs.  WDK rate-limits concurrent analysis requests, so serialize
      // tests within this project to avoid parallel enrichment calls.
      fullyParallel: false,
    },
    {
      name: "journey",
      testDir: "./e2e/journey",
      timeout: 180_000,
      // Journey tests run enrichment against live VEuPathDB WDK APIs.
      // WDK rate-limits concurrent analysis requests, so serialize these.
      fullyParallel: false,
    },
  ],

  // No webServer: both local and CI drive containers the recipe above starts.
  // Port 3000 serves the production build of the `runner` target, and the API
  // on port 8000 runs with PATHFINDER_CHAT_PROVIDER=mock from the e2e overlay.
});
