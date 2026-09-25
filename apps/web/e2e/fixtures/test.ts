import { test as base } from "@playwright/test";
import {
  type ApiClient,
  CSRF_HEADERS,
  clearUserData,
  createApiClient,
} from "./api-client";
import { ChatPage } from "../pages/chat.page";
import { SidebarPage } from "../pages/sidebar.page";
import { GraphPage } from "../pages/graph.page";
import { SitePickerComponent } from "../pages/site-picker.page";
import { SettingsPage } from "../pages/settings.page";
import { wdkTestToken } from "./wdk-account";
import * as fs from "node:fs";
import * as path from "node:path";

/** Test-scoped fixtures (fresh per test). */
type TestFixtures = {
  _autoCleanup: void;
  chatPage: ChatPage;
  sidebarPage: SidebarPage;
  graphPage: GraphPage;
  sitePicker: SitePickerComponent;
  settingsPage: SettingsPage;
  apiClient: ApiClient;
};

/** Worker-scoped fixtures (shared across tests in a worker). */
type WorkerFixtures = {
  workerStorageState: string;
};

export const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // Worker-scoped

  /**
   * Each worker signs in as its own PathFinder user (`/dev/login?user_id=worker-{N}`)
   * and carries the registered VEuPathDB token in the `Authorization` cookie.
   */
  workerStorageState: [
    async ({ browser }, use, workerInfo) => {
      const id = workerInfo.workerIndex;
      const dir = path.resolve("e2e/.auth");
      const fileName = path.join(dir, `worker-${id}.json`);

      // Always re-authenticate to ensure a clean session.
      fs.mkdirSync(dir, { recursive: true });

      // No page loads the app here: its own auth refresh would race the dev
      // login for the session cookie the storage state saves.
      const context = await browser.newContext();
      await context.addCookies([
        { name: "Authorization", value: wdkTestToken(), url: BASE_URL },
      ]);

      const resp = await context.request.post(
        `${BASE_URL}/api/v1/dev/login?user_id=worker-${id}`,
        { headers: CSRF_HEADERS },
      );
      if (!resp.ok()) {
        throw new Error(`dev-login failed for worker-${id}: ${resp.status()}`);
      }

      // Acknowledge the first-login eval-data notice once per worker, the way
      // a researcher does, so it is not over the app in every later spec.
      const req = context.request;
      const noticeResp = await req.patch(`${BASE_URL}/api/v1/me/privacy`, {
        headers: CSRF_HEADERS,
        data: { noticeSeen: true },
      });
      if (!noticeResp.ok()) {
        throw new Error(
          `eval-data notice acknowledgement failed for worker-${id}: ${noticeResp.status()}`,
        );
      }

      // Clean up stale data from previous runs for THIS worker's user.
      await clearUserData(req, BASE_URL);

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

  // Test-scoped: auto-cleanup

  /** Clear gene sets, strategies, and dismissed strategies before each test. */
  _autoCleanup: [
    async ({ context }, use) => {
      await clearUserData(context.request, BASE_URL);
      await use(undefined);
    },
    { auto: true },
  ],

  // Test-scoped: page objects
  chatPage: async ({ page }, use) => {
    await use(new ChatPage(page));
  },

  sidebarPage: async ({ page }, use) => {
    await use(new SidebarPage(page));
  },

  graphPage: async ({ page }, use) => {
    await use(new GraphPage(page));
  },

  sitePicker: async ({ page }, use) => {
    await use(new SitePickerComponent(page));
  },

  settingsPage: async ({ page }, use) => {
    await use(new SettingsPage(page));
  },

  // Test-scoped: API client for postcondition verification
  apiClient: async ({ page, context }, use) => {
    const baseURL = page.url().startsWith("http")
      ? new URL(page.url()).origin
      : BASE_URL;
    const client = await createApiClient(context, baseURL);
    await use(client);
    await client.dispose();
  },
});

export { expect } from "@playwright/test";
