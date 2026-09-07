import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { siteIsDown } from "./availability";

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

const ROWS: SiteResponse[] = [
  site({ id: "veupathdb", available: false, unavailableReason: "TimeoutError" }),
  site({ id: "plasmodb" }),
];

describe("siteIsDown", () => {
  it("is true for a site the api reports unavailable", () => {
    expect(siteIsDown(ROWS, "veupathdb")).toBe(true);
  });

  it("is false for a site the api reports available", () => {
    expect(siteIsDown(ROWS, "plasmodb")).toBe(false);
  });

  it("is false for a site the list does not name", () => {
    expect(siteIsDown(ROWS, "orthomcl")).toBe(false);
  });

  it("is false when the list is empty", () => {
    expect(siteIsDown([], "veupathdb")).toBe(false);
  });
});
