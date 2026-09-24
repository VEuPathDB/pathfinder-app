import { expect, request } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";

/**
 * One request per route pattern the suite enters. The production server loads
 * a route's module graph and renders it cold on the first request, so the
 * first spec to reach one pays a cost that has nothing to do with what it
 * asserts. The cost is per pattern, not per parameter value, so one site and
 * one id cover every conversation route.
 */
const ID = "00000000-0000-0000-0000-000000000001";
const SITE = "plasmodb";

const ROUTES = [
  "/",
  "/conversation",
  `/${SITE}/conversation`,
  `/${SITE}/conversation/${ID}`,
  `/${SITE}/conversation/${ID}/strategy`,
  `/${SITE}/conversation/${ID}/strategy/step/${ID}`,
  `/${SITE}/conversation/${ID}/eda`,
  `/${SITE}/saved`,
];

const COLD_RENDER_BUDGET_MS = 180_000;
const LISTEN_BUDGET_MS = 120_000;

/** Wait for the web container to accept connections. A restarted container
 *  resets the socket until its server binds the port. */
async function waitForServer(api: APIRequestContext): Promise<void> {
  await expect(async () => {
    const response = await api.get("/", { timeout: 30_000 });
    expect(response.status()).toBeLessThan(500);
  }).toPass({ timeout: LISTEN_BUDGET_MS, intervals: [1_000, 2_000, 5_000] });
}

const CATALOG_BUDGET_MS = 120_000;

/**
 * Wait for every site's catalog, without depending on any of them. The api is
 * healthy once one catalog is loaded, so a spec can otherwise open a site whose
 * catalog is still building and read its 503. A site that stays degraded is
 * reported and the suite runs anyway: its own specs fail, the rest do not.
 */
async function waitForSiteCatalogs(api: APIRequestContext): Promise<void> {
  const deadline = Date.now() + CATALOG_BUDGET_MS;
  let degraded: string[] = [];
  while (Date.now() < deadline) {
    const response = await api.get("/api/v1/sites", { timeout: 30_000 });
    if (response.ok()) {
      const rows = (await response.json()) as { id: string; available: boolean }[];
      degraded = rows.filter((row) => !row.available).map((row) => row.id);
      if (degraded.length === 0) {
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 5_000));
  }
  console.warn(`Sites with no loaded catalog: ${degraded.join(", ")}`);
}

const LOGIN_SITE = "plasmodb";

/**
 * Every worker acts as one registered VEuPathDB account through the
 * `Authorization` cookie. A shell that exports `WDK_TEST_TOKEN` supplies it
 * directly; a shell that exports the account's email and password instead
 * signs in once here, and the cookie the API sets becomes the token the
 * fixtures read. Environment set in global setup reaches every test.
 */
async function mintWdkTestToken(api: APIRequestContext): Promise<void> {
  if ((process.env["WDK_TEST_TOKEN"] ?? "") !== "") {
    return;
  }
  const email = process.env["WDK_TEST_EMAIL"] ?? "";
  const password = process.env["WDK_TEST_PASSWORD"] ?? "";
  if (email === "" || password === "") {
    return;
  }
  const response = await api.post("/api/v1/veupathdb/auth/login", {
    params: { siteId: LOGIN_SITE },
    data: { email, password },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok()) {
    throw new Error(
      `VEuPathDB login for the e2e account answered ${response.status()}`,
    );
  }
  const state = await api.storageState();
  const cookie = state.cookies.find((c) => c.name === "Authorization");
  if (cookie === undefined || cookie.value === "") {
    throw new Error("VEuPathDB login set no Authorization cookie");
  }
  process.env["WDK_TEST_TOKEN"] = cookie.value;
}

export default async function warmRoutes(): Promise<void> {
  const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
  const api = await request.newContext({ baseURL });
  try {
    await waitForServer(api);
    await mintWdkTestToken(api);
    await waitForSiteCatalogs(api);
    for (const route of ROUTES) {
      await api.get(route, { timeout: COLD_RENDER_BUDGET_MS });
    }
  } finally {
    await api.dispose();
  }
}
