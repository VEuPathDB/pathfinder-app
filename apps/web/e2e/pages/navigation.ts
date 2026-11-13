import { type Page, expect } from "@playwright/test";
import type { SiteResponse } from "@strategist/shared";

import { BASE_PATH } from "@/lib/basePath";

/**
 * Wall clock one route change needs. The dev server compiles a route the
 * first time a spec reaches it, and two workers can reach it at once, so a
 * cold conversation route takes far longer than a warm one.
 */
export const ROUTE_TIMEOUT_MS = 60_000;

/** Wait until the URL names `conversationId`. The chat view is keyed on the
 *  id in the URL, so an action taken before it moves runs against the
 *  conversation the click is leaving. */
export async function waitForConversationRoute(page: Page, conversationId: string) {
  await page.waitForURL(
    (url) => url.pathname.endsWith(`/conversation/${conversationId}`),
    { timeout: ROUTE_TIMEOUT_MS },
  );
}

/** The id of the conversation the URL names, once the router has put it
 *  there. A list position is a race with the sidebar refetch; the URL is not. */
export async function openConversationId(page: Page): Promise<string> {
  await page.waitForURL(/\/conversation\/[0-9a-fA-F-]{36}$/, {
    timeout: ROUTE_TIMEOUT_MS,
  });
  const id = new URL(page.url()).pathname.split("/").pop() ?? "";
  if (id === "") {
    throw new Error("the conversation route carries no id");
  }
  return id;
}

/** Wait until the URL names the draft chat route, which carries no id. */
export async function waitForDraftChatRoute(page: Page) {
  await page.waitForURL((url) => url.pathname.endsWith("/conversation"), {
    timeout: ROUTE_TIMEOUT_MS,
  });
}

/** Make the page's origin the website of `siteId`, as a site's own website does. */
export async function frameOnSite(page: Page, siteId: string) {
  await page.route(
    (url) => url.pathname === `${BASE_PATH}/api/v1/sites`,
    async (route) => {
      const response = await route.fetch();
      const sites = (await response.json()) as SiteResponse[];
      const { origin } = new URL(route.request().url());
      await route.fulfill({
        response,
        json: sites.map((site) =>
          site.id === siteId ? { ...site, siteOrigin: origin } : site,
        ),
      });
    },
  );
}

export async function gotoOnSite(page: Page, siteId: string, path: string) {
  await frameOnSite(page, siteId);
  await page.goto(path);
}

/** The site the app works on: the site at the page's origin, else the configured site. */
export async function currentSiteId(page: Page): Promise<string> {
  return page.evaluate(async (basePath) => {
    const sites = (await (await fetch(`${basePath}/api/v1/sites`)).json()) as {
      id: string;
      siteOrigin: string;
    }[];
    const config = (await (await fetch(`${basePath}/health/config`)).json()) as {
      siteId: string;
    };
    return (
      sites.find((site) => site.siteOrigin === window.location.origin)?.id ??
      config.siteId
    );
  }, BASE_PATH);
}

export async function expectCurrentSite(page: Page, siteId: string) {
  await expect
    .poll(() => currentSiteId(page), { timeout: ROUTE_TIMEOUT_MS })
    .toBe(siteId);
}
