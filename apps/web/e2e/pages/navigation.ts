import type { Page } from "@playwright/test";

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

const SESSION_STORE_KEY = "pathfinder-session-20260625";
const STORAGE_RESET_MARKER = "pf-local-reset-20260625";

export async function gotoOnSite(page: Page, siteId: string, path: string) {
  const pick = await page.addInitScript(
    ({ site, sessionKey, resetMarker }) => {
      window.localStorage.setItem(resetMarker, "1");
      window.localStorage.setItem(
        sessionKey,
        JSON.stringify({ state: { pickedSite: site }, version: 0 }),
      );
    },
    { site: siteId, sessionKey: SESSION_STORE_KEY, resetMarker: STORAGE_RESET_MARKER },
  );
  await page.goto(path);
  await pick.dispose();
}

export async function currentSiteId(page: Page): Promise<string> {
  const stored = await page.evaluate(
    (key) => window.localStorage.getItem(key),
    SESSION_STORE_KEY,
  );
  if (stored === null) {
    throw new Error("the app has stored no picked site");
  }
  const { state } = JSON.parse(stored) as { state: { pickedSite?: string } };
  if (state.pickedSite === undefined || state.pickedSite === "") {
    throw new Error("the stored session names no picked site");
  }
  return state.pickedSite;
}
