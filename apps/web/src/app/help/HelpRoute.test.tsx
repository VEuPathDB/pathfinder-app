/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

import { HelpRoute } from "./HelpRoute";

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

function renderWith(sites: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryDefaults(sitesOptions().queryKey, { staleTime: Infinity });
  queryClient.setQueryData(sitesOptions().queryKey, sites);
  return render(<HelpRoute />, { wrapper: Wrapper });
}

afterEach(() => {
  cleanup();
});

describe("HelpRoute", () => {
  it("shows no site switch on a component site's website", () => {
    const { container } = renderWith([
      site("veupathdb", "https://muharram.veupathdb.org", true),
      site("plasmodb", window.location.origin),
    ]);

    expect(screen.getByText(/Here, PathFinder works on PlasmoDB\./)).toBeVisible();
    expect(container).not.toHaveTextContent("Switch site");
  });

  it("names Switch site on the portal's website", () => {
    renderWith([
      site("veupathdb", window.location.origin, true),
      site("plasmodb", "https://muharram.plasmodb.org"),
    ]);

    expect(
      screen.getByText(/choose Switch site at the bottom of the left bar/),
    ).toBeVisible();
  });
});
