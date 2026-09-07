import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { chooseEntrySite } from "./entrySite";

function site(over: Partial<SiteResponse>): SiteResponse {
  return {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://plasmodb.org/plasmo",
    projectId: "PlasmoDB",
    isPortal: false,
    available: true,
    unavailableReason: null,
    ...over,
  };
}

const PORTAL = site({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
});

describe("chooseEntrySite", () => {
  it("picks the portal when the portal answers", () => {
    expect(
      chooseEntrySite([site({ id: "toxodb" }), PORTAL, site({ id: "plasmodb" })]),
    ).toEqual({ kind: "site", siteId: "veupathdb" });
  });

  it("picks the first available site in list order when the portal is degraded", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb" }),
      site({ id: "plasmodb" }),
    ];

    expect(chooseEntrySite(sites)).toEqual({ kind: "site", siteId: "toxodb" });
  });

  it("skips every degraded site before it picks one", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
      site({ id: "cryptodb" }),
    ];

    expect(chooseEntrySite(sites)).toEqual({ kind: "site", siteId: "cryptodb" });
  });

  it("names every degraded site when none answers", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
    ];

    expect(chooseEntrySite(sites)).toEqual({
      kind: "none",
      sites: ["veupathdb", "toxodb"],
    });
  });

  it("reports no site for an empty list", () => {
    expect(chooseEntrySite([])).toEqual({ kind: "none", sites: [] });
  });
});
