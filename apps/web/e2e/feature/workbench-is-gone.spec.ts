import { test, expect } from "../fixtures/test";

/**
 * The workbench page is removed: its address answers the app's 404, and the
 * nav rail links no workbench.
 */
test.describe("The workbench is gone", () => {
  test("a site's workbench address answers the app's 404", async ({ page, siteId }) => {
    const response = await page.goto(`/${siteId}/workbench`);

    expect(response?.status()).toBe(404);
    await expect(page.getByText("this page couldn't be found")).toBeVisible();
  });

  test("the nav rail links no workbench", async ({ page, chatPage }) => {
    await chatPage.goto();

    await expect(page.getByRole("link", { name: "Conversation" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Workbench" })).toHaveCount(0);
  });
});
