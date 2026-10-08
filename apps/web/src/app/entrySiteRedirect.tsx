import { redirect } from "next/navigation";
import { systemConfigResponseSchema } from "@pathfinder/shared/generated/zod/systemConfigResponseSchema";

import { StartupScreen } from "@/app/components/StartupScreen";
import { requestJson } from "@/lib/api/http";
import { listSites } from "@/lib/api/sites";
import { chooseEntrySite } from "@/lib/sites/entrySite";

/**
 * Sends a site-less entry point to ``target`` on the deployment's site, or on
 * another site the api reports as available, and renders the startup screen
 * when none is.
 */
export async function redirectToEntrySite(
  target: (siteId: string) => string,
): Promise<React.ReactElement> {
  const [sites, config] = await Promise.all([
    listSites().catch(() => null),
    requestJson(systemConfigResponseSchema, "/health/config").catch(() => null),
  ]);
  if (sites === null || config === null) {
    return <StartupScreen status={{ kind: "unreachable" }} />;
  }
  const entry = chooseEntrySite(sites, config.siteId);
  if (entry.kind === "none") {
    return <StartupScreen status={{ kind: "no-sites", sites: entry.sites }} />;
  }
  redirect(target(entry.siteId));
}
