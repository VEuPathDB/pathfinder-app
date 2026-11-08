/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";

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
    offersAudits: false,
  };
}

function renderWith(sites: SiteResponse[]) {
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
  return render(<HelpRoute />, { wrapper: Wrapper });
}

afterEach(() => {
  cleanup();
});

describe("HelpRoute", () => {
  it("names the component site whose website it is on", () => {
    const { container } = renderWith([
      site("veupathdb", "https://muharram.veupathdb.org", true),
      site("plasmodb", window.location.origin),
    ]);

    expect(screen.getByText(/Here, PathFinder works on PlasmoDB\./)).toBeVisible();
    expect(container).not.toHaveTextContent("Switch site");
  });

  it("names the portal on the portal's website, and offers no site", () => {
    const { container } = renderWith([
      site("veupathdb", window.location.origin, true),
      site("plasmodb", "https://muharram.plasmodb.org"),
    ]);

    expect(screen.getByText(/Here, PathFinder works on VEuPathDB\./)).toBeVisible();
    expect(container).not.toHaveTextContent("Switch site");
  });

  it("names the configured site on a host no site names", () => {
    renderWith([site("plasmodb", "https://muharram.plasmodb.org")]);

    expect(screen.getByText(/Here, PathFinder works on ToxoDB\./)).toBeVisible();
  });
});
