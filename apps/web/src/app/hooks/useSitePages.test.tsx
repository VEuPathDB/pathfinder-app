/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";
import type { SystemConfigResponse } from "@pathfinder/shared/generated/types/SystemConfigResponse";

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

import { useSitePages } from "./useSitePages";

const CONFIG: SystemConfigResponse = {
  chatProvider: "mock",
  llmConfigured: true,
  providers: { openai: false, anthropic: false, google: false, ollama: false },
  siteId: "veupathdb",
  siteSignInUrl: "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login",
  sitePageUrl: "https://muharram.veupathdb.org/eupathdb.amuharram/app/pathfinder",
};

function site(id: string, origin: string, webapp: string): SiteResponse {
  return {
    id,
    name: id,
    displayName: id,
    baseUrl: `${origin}/${webapp}/service`,
    projectId: id,
    isPortal: false,
    siteOrigin: origin,
    signInUrl: `${origin}/${webapp}/app/user/login`,
    pageUrl: `${origin}/${webapp}/app/pathfinder`,
    available: true,
    unavailableReason: null,
  };
}

function pagesWith(sites: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  for (const [queryKey, data] of [
    [systemConfigQueryOptions().queryKey, CONFIG],
    [sitesOptions().queryKey, sites],
  ] as const) {
    queryClient.setQueryDefaults(queryKey, { staleTime: Infinity });
    queryClient.setQueryData(queryKey, data);
  }
  return renderHook(() => useSitePages(), { wrapper: Wrapper }).result.current;
}

describe("useSitePages", () => {
  it("signs in and frames on the site whose website is at this page's origin", () => {
    const framing = site("plasmodb", window.location.origin, "plasmo.amuharram");

    expect(pagesWith([framing])).toEqual({
      signInUrl: `${window.location.origin}/plasmo.amuharram/app/user/login`,
      pageUrl: `${window.location.origin}/plasmo.amuharram/app/pathfinder`,
    });
  });

  it("uses the deployment's pages when no website is at this page's origin", () => {
    const elsewhere = site(
      "plasmodb",
      "https://muharram.plasmodb.org",
      "plasmo.amuharram",
    );

    expect(pagesWith([elsewhere])).toEqual({
      signInUrl: CONFIG.siteSignInUrl,
      pageUrl: CONFIG.sitePageUrl,
    });
  });
});
