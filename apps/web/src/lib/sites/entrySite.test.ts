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
const PLASMO = site({ id: "plasmodb" });

describe("chooseEntrySite", () => {
  it("opens the deployment's site when it answers", () => {
    expect(chooseEntrySite([PORTAL, PLASMO], "plasmodb")).toEqual({
      kind: "site",
      siteId: "plasmodb",
    });
  });

  it("falls back to the portal when the deployment's site does not answer", () => {
    expect(
      chooseEntrySite([PORTAL, { ...PLASMO, available: false }], "plasmodb"),
    ).toEqual({ kind: "site", siteId: "veupathdb" });
  });

  it("falls back to the portal when the list does not carry the deployment's site", () => {
    expect(
      chooseEntrySite([site({ id: "toxodb" }), PORTAL, PLASMO], "giardiadb"),
    ).toEqual({ kind: "site", siteId: "veupathdb" });
  });

  it("picks the first available site in list order when the portal is degraded", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb" }),
      PLASMO,
    ];

    expect(chooseEntrySite(sites, "veupathdb")).toEqual({
      kind: "site",
      siteId: "toxodb",
    });
  });

  it("skips every degraded site before it picks one", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
      site({ id: "cryptodb" }),
    ];

    expect(chooseEntrySite(sites, "toxodb")).toEqual({
      kind: "site",
      siteId: "cryptodb",
    });
  });

  it("names every degraded site when none answers", () => {
    const sites = [
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
    ];

    expect(chooseEntrySite(sites, "veupathdb")).toEqual({
      kind: "none",
      sites: ["veupathdb", "toxodb"],
    });
  });

  it("reports no site for an empty list", () => {
    expect(chooseEntrySite([], "veupathdb")).toEqual({ kind: "none", sites: [] });
  });
});
