import { type BrowserContext, test as base } from "@playwright/test";
import {
  type ApiClient,
  CSRF_HEADERS,
  continuePastDataNotice,
  createApiClient,
} from "./api-client";
import { OwnedData } from "./owned-data";
import { ChatPage } from "../pages/chat.page";
import { SidebarPage } from "../pages/sidebar.page";
import { GraphPage } from "../pages/graph.page";
import { frameOnSite } from "../pages/navigation";
import { SettingsPage } from "../pages/settings.page";
import { accountToken, wdkTestToken } from "./wdk-account";
import { beginTest, endTest, holdTestToken, testToken, wireMode } from "./wire";
import { cassetteId } from "./wire-recordings";
import { BASE_PATH } from "@/lib/basePath";
import * as fs from "node:fs";
import * as path from "node:path";

/** Test-scoped fixtures (fresh per test). */
type TestFixtures = {
  _wire: string;
  _owned: OwnedData;
  _deleteOwned: void;
  chatPage: ChatPage;
  sidebarPage: SidebarPage;
  graphPage: GraphPage;
  settingsPage: SettingsPage;
  apiClient: ApiClient;
};

/** The site a project runs its specs on; `playwright.config.ts` sets it per project. */
export type SiteOption = {
  siteId: string;
};

/** Worker-scoped fixtures (shared across tests in a worker). */
type WorkerFixtures = SiteOption & {
  workerStorageState: string;
};

/** The origin the web app answers on; the website's login cookie sits at its root. */
const ORIGIN = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

/** The app's root: every page and every API call sits under the base path. */
export const BASE_URL = `${ORIGIN}${BASE_PATH}`;

/** The app's root as a `baseURL`, which a relative path resolves under. */
export const APP_ROOT = `${BASE_URL}/`;

/** The site a spec opens when its project names none. */
export const DEFAULT_SITE = "plasmodb";

export async function addWebsiteLogin(context: BrowserContext): Promise<void> {
  await context.addCookies([
    { name: "Authorization", value: wdkTestToken(), url: ORIGIN },
  ]);
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // Worker-scoped

  siteId: [DEFAULT_SITE, { option: true, scope: "worker" }],

  workerStorageState: [
    async ({ browser }, use, workerInfo) => {
      const id = workerInfo.workerIndex;
      const dir = path.resolve("e2e/.auth");
      const fileName = path.join(dir, `worker-${id}.json`);

      fs.mkdirSync(dir, { recursive: true });

      const context = await browser.newContext();
      const resp = await context.request.post(
        `${BASE_URL}/api/v1/dev/login?user_id=worker-${id}`,
        { headers: CSRF_HEADERS },
      );
      if (!resp.ok()) {
        throw new Error(`dev-login failed for worker-${id}: ${resp.status()}`);
      }

      await context.storageState({ path: fileName });
      await context.close();

      await use(fileName);
    },
    { scope: "worker" },
  ],

  /**
   * Override Playwright's built-in storageState so every test in this
   * worker uses the per-worker auth cookie.
   */
  storageState: ({ workerStorageState }, use) => use(workerStorageState),

  _wire: [
    async ({}, use, testInfo) => {
      const file = path.relative(testInfo.project.testDir, testInfo.file);
      const cassette = cassetteId(
        testInfo.project.name,
        file,
        testInfo.titlePath.slice(1),
      );
      await beginTest(cassette);
      holdTestToken(wireMode() === "replay" ? testToken(cassette) : accountToken());
      try {
        await use(cassette);
      } finally {
        holdTestToken("");
      }
      const report = await endTest(
        cassette,
        testInfo.status === testInfo.expectedStatus,
      );
      if (report !== "") {
        throw new Error(
          `${report}\n  The app sends something new: record this test on cedar:\n` +
            `  scripts/e2e-wire.sh record --test '${file}:${testInfo.line}'`,
        );
      }
    },
    { auto: true, timeout: 60_000 },
  ],

  _owned: async ({}, use) => {
    await use(new OwnedData());
  },

  context: async ({ context, _owned, _wire }, use) => {
    await addWebsiteLogin(context);
    const notice = await continuePastDataNotice(context.request, BASE_URL);
    if (!notice.ok()) {
      throw new Error(`data notice for ${_wire}: ${notice.status()}`);
    }
    _owned.watchPages(context);
    Object.defineProperty(context, "request", { value: _owned.track(context.request) });
    await use(context);
  },

  _deleteOwned: [
    async ({ context, _owned, _wire }, use) => {
      await use(undefined);
      await _owned.deleteAll(context.request, BASE_URL);
    },
    { auto: true, timeout: 240_000 },
  ],

  // Test-scoped: page objects
  chatPage: async ({ page }, use) => {
    await use(new ChatPage(page));
  },

  page: async ({ page, siteId }, use) => {
    await frameOnSite(page, siteId);
    await use(page);
  },

  sidebarPage: async ({ page }, use) => {
    await use(new SidebarPage(page));
  },

  graphPage: async ({ page }, use) => {
    await use(new GraphPage(page));
  },

  settingsPage: async ({ page }, use) => {
    await use(new SettingsPage(page));
  },

  // Test-scoped: API client for postcondition verification
  apiClient: async ({ context, _owned }, use) => {
    const client = await createApiClient(context, APP_ROOT);
    await use(_owned.track(client));
    await client.dispose();
  },
});

export { expect } from "@playwright/test";
