import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { currentSiteId, lockedSite } from "./currentSite";

function site(id: string, origin: string, isPortal = false): SiteResponse {
  return {
    id,
    name: id,
    displayName: id,
    baseUrl: `${origin}/${id}/service`,
    projectId: id,
    isPortal,
    siteOrigin: origin,
    signInUrl: `${origin}/${id}/app/user/login`,
    pageUrl: `${origin}/${id}/app/pathfinder`,
    available: true,
    unavailableReason: null,
  };
}

const PORTAL = site("veupathdb", "https://muharram.veupathdb.org", true);
const PLASMO = site("plasmodb", "https://muharram.plasmodb.org");
const TOXO = site("toxodb", "https://q2.toxodb.org");
const SITES = [PORTAL, PLASMO, TOXO];

describe("lockedSite", () => {
  it("is the component site whose website is at the page's origin", () => {
    expect(lockedSite(SITES, "https://muharram.plasmodb.org")?.id).toBe("plasmodb");
  });

  it("is no site on the portal's website", () => {
    expect(lockedSite(SITES, "https://muharram.veupathdb.org")?.id).toBe(undefined);
  });

  it("is no site on a host no site names", () => {
    expect(lockedSite(SITES, "http://localhost:3000")?.id).toBe(undefined);
  });

  it("is no site before the page's origin is known", () => {
    expect(lockedSite(SITES, null)?.id).toBe(undefined);
  });
});

describe("currentSiteId", () => {
  it("is the locked site, whatever is picked or open", () => {
    expect(
      currentSiteId({
        sites: SITES,
        origin: "https://muharram.plasmodb.org",
        picked: "veupathdb",
        conversationSite: "toxodb",
      }),
    ).toBe("plasmodb");
  });

  it("is the open conversation's site on the portal's website", () => {
    expect(
      currentSiteId({
        sites: SITES,
        origin: "https://muharram.veupathdb.org",
        picked: "veupathdb",
        conversationSite: "toxodb",
      }),
    ).toBe("toxodb");
  });

  it("is the picked site on the portal's website with no conversation open", () => {
    expect(
      currentSiteId({
        sites: SITES,
        origin: "https://muharram.veupathdb.org",
        picked: "toxodb",
        conversationSite: null,
      }),
    ).toBe("toxodb");
  });

  it("is the picked site on a host no site names", () => {
    expect(
      currentSiteId({
        sites: SITES,
        origin: "http://localhost:3000",
        picked: "plasmodb",
        conversationSite: null,
      }),
    ).toBe("plasmodb");
  });
});
