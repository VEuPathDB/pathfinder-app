import { test, expect } from "../fixtures/test";

interface SiteRow {
  id: string;
  isPortal: boolean;
  available: boolean;
}

/** The site the entry flow opens: the portal when it answers, else the first
 *  site the API reports available, in the list's own order. */
function entrySite(sites: SiteRow[]): SiteRow {
  const available = sites.filter((s) => s.available);
  const entry = available.find((s) => s.isPortal) ?? available[0];
  if (entry === undefined) throw new Error("the API reports no available site");
  return entry;
}

test.describe("Site Switching", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("the default site is the one the API reports available", async ({
    sitePicker,
    apiClient,
  }) => {
    const resp = await apiClient.get("/api/v1/sites");
    expect(resp.ok()).toBeTruthy();
    const sites = (await resp.json()) as SiteRow[];
    expect(sites.length).toBeGreaterThan(0);
    const siteIds = sites.map((s) => s.id);
    expect(siteIds).toContain("plasmodb");
    expect(siteIds).toContain("toxodb");
    expect(siteIds).toContain("cryptodb");

    await sitePicker.expectCurrentSite(entrySite(sites).id);
  });

  test("switching the site updates the picker, and switching back restores it", async ({
    sitePicker,
    page,
  }) => {
    await expect(page.getByRole("button", { name: /switch database/i })).toBeVisible({
      timeout: 5_000,
    });
    await sitePicker.selectSite("toxodb");
    await sitePicker.expectCurrentSite("toxodb");

    await sitePicker.selectSite("plasmodb");
    await sitePicker.expectCurrentSite("plasmodb");
  });
});
