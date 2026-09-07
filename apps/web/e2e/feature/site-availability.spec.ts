import { expect, test } from "@playwright/test";

/**
 * Readiness is about the api process, not about VEuPathDB's uptime: it answers
 * 200 while at least one site catalog is loaded, and every site it lists says
 * whether it answers. The degraded path itself is pinned by the api's unit and
 * route tests, because a spec cannot take a VEuPathDB site down.
 */
interface SiteRow {
  id: string;
  available: boolean;
  unavailableReason: string | null;
}

test.describe("Site availability", () => {
  test("readiness is served and every site reports whether it answers", async ({
    request,
  }) => {
    const ready = await request.get("/health/ready");
    expect(ready.status()).toBe(200);
    const readyBody = (await ready.json()) as {
      status: string;
      notReady: string[];
      degraded: string[];
    };
    expect(readyBody.status).toBe("healthy");
    expect(readyBody.notReady).toEqual([]);

    const sites = await request.get("/api/v1/sites");
    expect(sites.status()).toBe(200);
    const rows = (await sites.json()) as SiteRow[];
    expect(rows.length).toBeGreaterThan(0);

    // Availability is total: a site is unavailable exactly when it carries a
    // reason. The two calls are separate, and a retry can clear a site between
    // them, so the readiness body is only checked to name configured sites.
    for (const row of rows) {
      expect(row.available).toBe(row.unavailableReason === null);
    }
    const ids = rows.map((row) => row.id);
    for (const degraded of readyBody.degraded) {
      expect(ids).toContain(degraded);
    }
    expect(rows.some((row) => row.available)).toBe(true);
  });

  test("the bare root lands on a site the api reports as available", async ({
    page,
    request,
  }) => {
    const sites = await request.get("/api/v1/sites");
    expect(sites.status()).toBe(200);
    const rows = (await sites.json()) as SiteRow[];
    const available = rows.filter((row) => row.available).map((row) => row.id);
    const unavailable = rows.filter((row) => !row.available).map((row) => row.id);
    expect(available.length).toBeGreaterThan(0);

    await page.goto("/");
    await page.waitForURL(/\/[^/]+\/conversation/);
    const landedOn = new URL(page.url()).pathname.split("/")[1];

    expect(available).toContain(landedOn);
    expect(unavailable).not.toContain(landedOn);
  });
});
