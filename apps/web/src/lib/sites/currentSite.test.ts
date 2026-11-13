import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@strategist/shared";

import { currentSiteId } from "./currentSite";

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
    offersAudits: false,
  };
}

const PORTAL = site("veupathdb", "https://muharram.veupathdb.org", true);
const PLASMO = site("plasmodb", "https://muharram.plasmodb.org");
const TOXO = site("toxodb", "https://q2.toxodb.org");
const SITES = [PORTAL, PLASMO, TOXO];

describe("currentSiteId", () => {
  it("is the component site whose website is at the page's origin", () => {
    expect(currentSiteId(SITES, "https://muharram.plasmodb.org", "veupathdb")).toBe(
      "plasmodb",
    );
  });

  it("is the portal on the portal's website", () => {
    expect(currentSiteId(SITES, "https://muharram.veupathdb.org", "toxodb")).toBe(
      "veupathdb",
    );
  });

  it("is the configured site on a host no site names", () => {
    expect(currentSiteId(SITES, "http://localhost:3000", "toxodb")).toBe("toxodb");
  });

  it("is the configured site before the page's origin is known", () => {
    expect(currentSiteId(SITES, null, "toxodb")).toBe("toxodb");
  });
});
