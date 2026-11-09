import { APP_ROOT, test, expect } from "../fixtures/test";
import { createApiClient } from "../fixtures/api-client";
import { seedStrategy } from "../fixtures/strategy-builds";
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
});
