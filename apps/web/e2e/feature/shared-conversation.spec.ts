import { APP_ROOT, test, expect } from "../fixtures/test";
import { createApiClient } from "../fixtures/api-client";
import {
  PRIVATE_LIST_ID,
  seedStrategy,
  seedStrategyWithAList,
} from "../fixtures/strategy-builds";
import { signInAsWdkAccount } from "../fixtures/website-login";

test.describe("A shared conversation", () => {
  test("opens read-only for a viewer with no sign-in, and behind its password once private", async ({
    browser,
    context,
    siteId,
  }) => {
    await signInAsWdkAccount(context);
    const api = await createApiClient(context, APP_ROOT);
    const { conversationId } = await seedStrategy(api, siteId);
    const share = `api/v1/conversations/${conversationId}/share`;
    const viewer = await browser.newContext({ baseURL: APP_ROOT });

    try {
      const opened = await api.put(share, { data: { public: true, allowCopy: false } });
      expect(opened.status()).toBe(200);
      const { share: link } = (await opened.json()) as { share: { token: string } };
      const page = await viewer.newPage();

      await page.goto(`shared/${link.token}`);
      await expect(
        page.getByRole("heading", { name: "Smoke test strategy" }),
      ).toBeVisible({ timeout: 30_000 });
      await expect(page.getByTestId("shared-read-only")).toHaveText("Read-only");
      await expect(page.getByRole("textbox")).toHaveCount(0);

      const locked = await api.put(share, {
        data: { public: false, allowCopy: false },
      });
      const { password } = (await locked.json()) as { password: string };
      await page.reload();
      await page.getByLabel("Password").fill(password);
      await page.getByRole("button", { name: "Open" }).click();
      await expect(
        page.getByRole("heading", { name: "Smoke test strategy" }),
      ).toBeVisible({ timeout: 30_000 });

      expect((await api.delete(share)).status()).toBe(204);
      await page.reload();
      await expect(page.getByTestId("shared-gone")).toHaveText(
        "This link is no longer shared.",
      );
    } finally {
      await viewer.close();
      await api.delete(`api/v1/conversations/${conversationId}`);
      await api.dispose();
    }
  });

  test("shows the strategy read-only and keeps a private list out of the page", async ({
    browser,
    context,
    siteId,
  }) => {
    await signInAsWdkAccount(context);
    const api = await createApiClient(context, APP_ROOT);
    const { conversationId } = await seedStrategyWithAList(api, siteId);
    const share = `api/v1/conversations/${conversationId}/share`;
    const viewer = await browser.newContext({ baseURL: APP_ROOT });

    try {
      const opened = await api.put(share, { data: { public: true, allowCopy: false } });
      expect(opened.status()).toBe(200);
      const { share: link } = (await opened.json()) as {
        share: { token: string; includeContext: boolean };
      };
      expect(link.includeContext).toBe(true);
      const page = await viewer.newPage();
      const served = page.waitForResponse((response) =>
        response.url().endsWith(`/shared/${link.token}/context`),
      );

      await page.goto(`shared/${link.token}`);
      expect(await (await served).text()).not.toContain(PRIVATE_LIST_ID);
      await page.getByRole("button", { name: "Open Strategy" }).click();

      await expect(page.getByTestId("rail-strategy-panel")).toBeVisible();
      await expect(page.getByTestId("rail-strategy-panel")).toContainText(
        "All kinase transcripts",
      );
      await expect(page.getByText("Private list")).toHaveCount(1);
      await expect(page.getByTestId("rail-strategy-open")).toHaveCount(0);
      await expect(page.getByTestId("rail-strategy-refresh")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Step actions" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: /^Open strategy on / })).toHaveCount(
        0,
      );
      await expect(page.getByRole("button", { name: "Share" })).toHaveCount(0);
      expect(await page.content()).not.toContain(PRIVATE_LIST_ID);
    } finally {
      await viewer.close();
      await api.delete(`api/v1/conversations/${conversationId}`);
      await api.dispose();
    }
  });
});
