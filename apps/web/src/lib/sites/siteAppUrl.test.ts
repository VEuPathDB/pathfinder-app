import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { siteAppUrl } from "./siteAppUrl";

function site(baseUrl: string): SiteResponse {
  return {
    id: "toxodb",
    name: "ToxoDB",
    displayName: "ToxoDB (Toxoplasma)",
    baseUrl,
    projectId: "ToxoDB",
    isPortal: false,
    siteOrigin: "https://qa.toxodb.org",
    signInUrl: "https://qa.toxodb.org/toxo.qa/app/user/login",
    pageUrl: "https://qa.toxodb.org/toxo.qa/app/pathfinder",
    available: true,
    unavailableReason: null,
  };
}

describe("siteAppUrl", () => {
  it("is the website a service base URL serves", () => {
    expect(siteAppUrl(site("https://qa.toxodb.org/toxo.qa/service"), "/app/x")).toBe(
      "https://qa.toxodb.org/toxo.qa/app/x",
    );
  });

  it("keeps a base URL that names no service path", () => {
    expect(siteAppUrl(site("https://qa.toxodb.org/toxo.qa"), "/app/x")).toBe(
      "https://qa.toxodb.org/toxo.qa/app/x",
    );
  });
});
