import type { BrowserContext } from "@playwright/test";

interface SiteRow {
  id: string;
  isPortal: boolean;
  available: boolean;
}

/**
 * The site the app's entry flow opens: the portal when its catalog is loaded,
 * else the first site the API reports available, in the list's own order. A
 * spec that names a site must ask for this one, because a VEuPathDB site can
 * be down while the rest answer.
 */
export async function entrySiteId(
  context: BrowserContext,
  baseUrl: string,
): Promise<string> {
  const resp = await context.request.get(`${baseUrl}/api/v1/sites`);
  if (!resp.ok()) throw new Error(`sites failed: ${resp.status()}`);
  const rows = (await resp.json()) as SiteRow[];
  const available = rows.filter((row) => row.available);
  const entry = available.find((row) => row.isPortal) ?? available[0];
  if (entry === undefined) throw new Error("the API reports no available site");
  return entry.id;
}
