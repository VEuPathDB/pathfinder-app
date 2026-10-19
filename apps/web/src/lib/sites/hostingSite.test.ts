import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { hostingSite } from "./hostingSite";

function site(id: string, host: string, webapp: string): SiteResponse {
  return {
    id,
    name: id,
    displayName: id,
    baseUrl: `https://${host}/${webapp}/service`,
    projectId: id,
    isPortal: id === "veupathdb",
    siteOrigin: `https://${host}`,
    signInUrl: `https://${host}/${webapp}/app/user/login`,
    pageUrl: `https://${host}/${webapp}/app/pathfinder`,
    available: true,
    unavailableReason: null,
  };
}

const PORTAL = site("veupathdb", "muharram.veupathdb.org", "eupathdb.amuharram");
const PLASMO = site("plasmodb", "muharram.plasmodb.org", "plasmo.amuharram");

describe("hostingSite", () => {
  it("is the site whose website is at the page's origin", () => {
    expect(hostingSite([PORTAL, PLASMO], "https://muharram.plasmodb.org")?.id).toBe(
      "plasmodb",
    );
  });

  it("is no site when no website is at the page's origin", () => {
    expect(hostingSite([PORTAL, PLASMO], "http://localhost:3000")?.id).toBe(undefined);
  });
});
