import { expect, request } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";

import { BASE_PATH } from "../src/lib/basePath";
import { clearUserData, continuePastDataNotice } from "./fixtures/api-client";
import { accountToken, siteLoginToken } from "./fixtures/wdk-account";
import {
  type WireMode,
  readManifest,
  shareSigningKey,
  wireMode,
  wireServes,
} from "./fixtures/wire";
import { stalenessLines } from "./fixtures/wire-recordings";

/**
 * One request per route pattern the suite enters. The production server loads
 * a route's module graph and renders it cold on the first request, so the
 * first spec to reach one pays a cost that has nothing to do with what it
 * asserts.
 */
const ID = "00000000-0000-0000-0000-000000000001";

const ROUTES = [
  "./",
  "conversation",
  `conversation/${ID}`,
  `conversation/${ID}/strategy`,
  `conversation/${ID}/strategy/step/${ID}`,
  `conversation/${ID}/eda`,
  "saved",
];

const COLD_RENDER_BUDGET_MS = 180_000;
const LISTEN_BUDGET_MS = 120_000;

/** Wait for the web container to accept connections. A restarted container
 *  resets the socket until its server binds the port. */
async function waitForServer(api: APIRequestContext): Promise<void> {
  await expect(async () => {
    const response = await api.get("./", { timeout: 30_000 });
    expect(response.status()).toBeLessThan(500);
  }).toPass({ timeout: LISTEN_BUDGET_MS, intervals: [1_000, 2_000, 5_000] });
}

const CATALOG_BUDGET_MS = 120_000;

/**
 * Wait for every site's catalog, without depending on any of them. The api is
 * healthy once one catalog is loaded, so a spec can otherwise open a site whose
 * catalog is still building and read its 503. In replay every catalog comes
 * from a committed snapshot, so a degraded site fails the run; in record it is
 * reported and the suite runs anyway.
 */
async function waitForSiteCatalogs(
  api: APIRequestContext,
  mode: WireMode,
): Promise<void> {
  const deadline = Date.now() + CATALOG_BUDGET_MS;
  let degraded: string[] = [];
  while (Date.now() < deadline) {
    const response = await api.get("api/v1/sites", { timeout: 30_000 });
    if (response.ok()) {
      const rows = (await response.json()) as { id: string; available: boolean }[];
      degraded = rows.filter((row) => !row.available).map((row) => row.id);
      if (degraded.length === 0) {
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 5_000));
  }
  if (mode === "replay") {
    throw new Error(
      `Sites with no loaded catalog: ${degraded.join(", ")}. Their snapshots in ` +
        "e2e/wire/catalogs did not load; a refresh rebuilds them.",
    );
  }
  console.warn(`Sites with no loaded catalog: ${degraded.join(", ")}`);
}

const LOGIN_SITE = "plasmodb";

/**
 * A record run acts as one registered VEuPathDB account through the
 * `Authorization` cookie. A shell that exports `WDK_TEST_TOKEN` supplies it
 * directly; a shell that exports the account's email and password instead
 * signs in once here at the site's own login, as the website does, and that
 * token becomes the one the fixtures read. Environment set in global setup
 * reaches every test.
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
  const response = await api.get("api/v1/sites");
  if (!response.ok()) {
    throw new Error(`the site list answered ${response.status()}`);
  }
  const rows = (await response.json()) as { id: string; baseUrl: string }[];
  const site = rows.find((row) => row.id === LOGIN_SITE);
  if (site === undefined) {
    throw new Error(`the api lists no site ${LOGIN_SITE}`);
  }
  process.env["WDK_TEST_TOKEN"] = await siteLoginToken(site.baseUrl, email, password);
}

/** Every test deletes what it made, so a record run starts the account empty once. */
async function clearTheAccount(origin: string): Promise<void> {
  const account = await request.newContext({
    extraHTTPHeaders: { cookie: `Authorization=${accountToken()}` },
  });
  try {
    const appRoot = `${origin}${BASE_PATH}`;
    const notice = await continuePastDataNotice(account, appRoot);
    if (!notice.ok()) {
      throw new Error(`the data notice answered ${notice.status()}`);
    }
    await clearUserData(account, appRoot);
  } finally {
    await account.dispose();
  }
}

export default async function warmRoutes(): Promise<void> {
  const origin = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
  const baseURL = `${origin}${BASE_PATH}/`;
  const api = await request.newContext({ baseURL });
  const mode = wireMode();
  try {
    await wireServes(mode);
    await waitForServer(api);
    await waitForSiteCatalogs(api, mode);
    if (mode === "replay") {
      await shareSigningKey();
      process.stdout.write(
        `${stalenessLines(readManifest(), new Date()).join("\n")}\n`,
      );
    } else {
      await mintWdkTestToken(api);
      await clearTheAccount(origin);
    }
    for (const route of ROUTES) {
      await api.get(route, { timeout: COLD_RENDER_BUDGET_MS });
    }
  } finally {
    await api.dispose();
  }
}
