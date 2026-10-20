/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

vi.mock("next/navigation", () => ({ usePathname: () => "/conversation" }));

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

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
  };
}

function currentSiteWith(sites: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryDefaults(sitesOptions().queryKey, { staleTime: Infinity });
  queryClient.setQueryData(sitesOptions().queryKey, sites);
  const { siteId, locked } = renderHook(() => useCurrentSite(), { wrapper: Wrapper })
    .result.current;
  return { siteId, lockedTo: locked?.id ?? null };
}

beforeEach(() => {
  useSessionStore.setState({ pickedSite: "toxodb" });
});

describe("useCurrentSite", () => {
  it("is locked to the component site whose website frames PathFinder", () => {
    expect(
      currentSiteWith([
        site("veupathdb", "https://muharram.veupathdb.org", true),
        site("plasmodb", window.location.origin),
      ]),
    ).toEqual({ siteId: "plasmodb", lockedTo: "plasmodb" });
  });

  it("is the picked site on the portal's website", () => {
    expect(
      currentSiteWith([
        site("veupathdb", window.location.origin, true),
        site("plasmodb", "https://muharram.plasmodb.org"),
      ]),
    ).toEqual({ siteId: "toxodb", lockedTo: null });
  });
});
