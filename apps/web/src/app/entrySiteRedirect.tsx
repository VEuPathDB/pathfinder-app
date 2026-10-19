import { systemConfigResponseSchema } from "@pathfinder/shared/generated/zod/systemConfigResponseSchema";

import { EntrySiteRedirect } from "@/app/components/EntrySiteRedirect";
import { StartupScreen } from "@/app/components/StartupScreen";
import { requestJson } from "@/lib/api/http";
import { listSites } from "@/lib/api/sites";
import { chooseEntrySite } from "@/lib/sites/entrySite";

/**
 * Sends a site-less entry point to the chat of the site whose website frames
 * PathFinder, or of the deployment's site, or of another site the api reports
 * as available, and renders the startup screen when none is.
 */
export async function redirectToEntrySite(): Promise<React.ReactElement> {
  const [sites, config] = await Promise.all([
    listSites().catch(() => null),
    requestJson(systemConfigResponseSchema, "/health/config").catch(() => null),
  ]);
  if (sites === null || config === null) {
    return <StartupScreen status={{ kind: "unreachable" }} />;
  }
  const entry = chooseEntrySite(sites, config.siteId, null);
  if (entry.kind === "none") {
    return <StartupScreen status={{ kind: "no-sites", sites: entry.sites }} />;
  }
  return <EntrySiteRedirect sites={sites} deploymentSiteId={config.siteId} />;
}
