import { redirect } from "next/navigation";

import { StartupScreen } from "@/app/components/StartupScreen";
import { listSites } from "@/lib/api/sites";
import { chooseEntrySite } from "@/lib/sites/entrySite";

/**
 * Sends a site-less entry point to ``target`` on a site the api reports as
 * available, and renders the startup screen when none is.
 */
export async function redirectToEntrySite(
  target: (siteId: string) => string,
): Promise<React.ReactElement> {
  const sites = await listSites().catch(() => null);
  if (sites === null) {
    return <StartupScreen status={{ kind: "unreachable" }} />;
  }
  const entry = chooseEntrySite(sites);
  if (entry.kind === "none") {
    return <StartupScreen status={{ kind: "no-sites", sites: entry.sites }} />;
  }
  redirect(target(entry.siteId));
}
