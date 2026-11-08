/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";

vi.mock("next/navigation", () => ({ usePathname: () => "/conversation" }));

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

import { useCurrentSite } from "./useCurrentSite";

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

function currentSiteWith(sites: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryDefaults(sitesOptions().queryKey, { staleTime: Infinity });
  queryClient.setQueryData(sitesOptions().queryKey, sites);
  queryClient.setQueryDefaults(systemConfigQueryOptions().queryKey, {
    staleTime: Infinity,
  });
  queryClient.setQueryData(systemConfigQueryOptions().queryKey, {
    chatProvider: "mock",
    llmConfigured: true,
    providers: { openai: false, anthropic: false, google: false, ollama: false },
    siteId: "toxodb",
    siteSignInUrl: "https://qa.toxodb.org/toxo.qa/app/user/login",
    sitePageUrl: "https://qa.toxodb.org/toxo.qa/app/pathfinder",
  });
  return renderHook(() => useCurrentSite(), { wrapper: Wrapper }).result.current;
}

describe("useCurrentSite", () => {
  it("offers audits where the current site does", () => {
    const offering = {
      ...site("plasmodb", window.location.origin),
      offersAudits: true,
    };
    expect(currentSiteWith([offering]).offersAudits).toBe(true);
  });

  it("is the component site whose website frames PathFinder", () => {
    expect(
      currentSiteWith([
        site("veupathdb", "https://muharram.veupathdb.org", true),
        site("plasmodb", window.location.origin),
      ]),
    ).toEqual({
      siteId: "plasmodb",
      isPortal: false,
      conversationSite: null,
      offersAudits: false,
    });
  });

  it("is the portal on the portal's website", () => {
    expect(
      currentSiteWith([
        site("veupathdb", window.location.origin, true),
        site("plasmodb", "https://muharram.plasmodb.org"),
      ]),
    ).toEqual({
      siteId: "veupathdb",
      isPortal: true,
      conversationSite: null,
      offersAudits: false,
    });
  });

  it("is the deployment's configured site on a host no site names", () => {
    expect(
      currentSiteWith([
        site("veupathdb", "https://muharram.veupathdb.org", true),
        site("toxodb", "https://muharram.toxodb.org"),
      ]),
    ).toEqual({
      siteId: "toxodb",
      isPortal: false,
      conversationSite: null,
      offersAudits: false,
    });
  });
});
