import type { BrowserContext } from "@playwright/test";

interface SiteRow {
  id: string;
  isPortal: boolean;
  available: boolean;
}

/**
 * A site the API reports available: the portal when its catalog is loaded,
 * else the first available site, in the list's own order. A spec that needs a
 * reachable site asks for this one, because a VEuPathDB site can be down while
 * the rest answer.
 */
export async function availableSiteId(
  context: BrowserContext,
  baseUrl: string,
): Promise<string> {
  const resp = await context.request.get(`${baseUrl}/api/v1/sites`);
  if (!resp.ok()) throw new Error(`sites failed: ${resp.status()}`);
  const rows = (await resp.json()) as SiteRow[];
  const available = rows.filter((row) => row.available);
  const site = available.find((row) => row.isPortal) ?? available[0];
  if (site === undefined) throw new Error("the API reports no available site");
  return site.id;
}
