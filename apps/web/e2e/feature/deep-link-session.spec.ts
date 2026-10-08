/**
 * A thread opened with the website's login and no PathFinder session cookie
 * renders once the shell mints the session, also after a website sign-out.
 */

import type { Page } from "@playwright/test";

import { QUERY_STALE_TIME_MS } from "@/lib/query/staleTime";

import { APP_ROOT, addWebsiteLogin, test, expect } from "../fixtures/test";
import { createApiClient } from "../fixtures/api-client";
import { seedStrategy } from "../fixtures/strategy-builds";
import { signInAsWdkAccount } from "../fixtures/website-login";

test.describe("A deep link without a PathFinder session", () => {
  test("renders the thread and the quota meter", async ({ page, context, siteId }) => {
    await signInAsWdkAccount(context, siteId);
    const api = await createApiClient(context, APP_ROOT);
    const { conversationId } = await seedStrategy(api, siteId);

    await context.clearCookies({ name: "pathfinder-auth" });
    const refused: string[] = [];
    page.on("response", (response) => {
      if (response.status() === 401) refused.push(response.url());
    });

    try {
      await page.goto(`${siteId}/conversation/${conversationId}`);

      await expect(page.getByTestId("message-composer")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByRole("img", { name: "Monthly spend" })).toBeVisible();
      expect(refused).toEqual([]);
    } finally {
      await api.delete(`api/v1/conversations/${conversationId}`);
      await api.dispose();
    }
  });

  test("mints the session again when the website signs in after a sign-out", async ({
    page,
    context,
    siteId,
  }) => {
    await signInAsWdkAccount(context, siteId);
    const api = await createApiClient(context, APP_ROOT);
    const { conversationId } = await seedStrategy(api, siteId);
    await page.clock.install();

    try {
      await page.goto(`${siteId}/conversation/${conversationId}`);
      await expect(page.getByTestId("message-composer")).toBeVisible({
        timeout: 30_000,
      });

      await context.clearCookies();
      await askStatusAgain(page);
      await expect(page.getByTestId("signed-out-notice")).toBeVisible();

      const requests: string[] = [];
      page.on("response", (response) => {
        const path = new URL(response.url()).pathname;
        requests.push(`${response.request().method()} ${response.status()} ${path}`);
      });
      await addWebsiteLogin(context);
      await askStatusAgain(page);

      await expect(page.getByTestId("message-composer")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByRole("img", { name: "Monthly spend" })).toBeVisible();
      const refresh = requests.indexOf(
        "POST 200 /pathfinder/api/v1/veupathdb/auth/refresh",
      );
      const quota = requests.indexOf("GET 200 /pathfinder/api/v1/me/quota");
      expect(refresh).toBeGreaterThan(-1);
      expect(quota).toBeGreaterThan(refresh);
      expect(requests.filter((line) => line.includes(" 401 "))).toEqual([]);
    } finally {
      await api.delete(`api/v1/conversations/${conversationId}`);
      await api.dispose();
    }
  });
});

/** Ages the cached sign-in status past its stale time and returns focus to the tab. */
async function askStatusAgain(page: Page): Promise<void> {
  await page.clock.fastForward(QUERY_STALE_TIME_MS + 1_000);
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
}
