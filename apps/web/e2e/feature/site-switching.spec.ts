import { test, expect } from "../fixtures/test";

interface SiteRow {
  id: string;
}

test.describe("Site Switching", { tag: "@named-site" }, () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("a first visit works on the portal", async ({ sitePicker, apiClient }) => {
    const resp = await apiClient.get("api/v1/sites");
    expect(resp.ok()).toBeTruthy();
    const sites = (await resp.json()) as SiteRow[];
    const siteIds = sites.map((s) => s.id);
    expect(siteIds).toContain("veupathdb");
    expect(siteIds).toContain("plasmodb");
    expect(siteIds).toContain("toxodb");
    expect(siteIds).toContain("cryptodb");

    await sitePicker.expectCurrentSite("veupathdb");
  });

  test("a site picked from the switcher stays picked across a reload", async ({
    page,
    chatPage,
    sitePicker,
  }) => {
    await sitePicker.selectSite("toxodb");
    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await sitePicker.expectCurrentSite("toxodb");
  });
});
