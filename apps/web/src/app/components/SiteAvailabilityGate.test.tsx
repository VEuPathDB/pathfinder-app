/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";
import { SiteAvailabilityGate } from "./SiteAvailabilityGate";

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

const PORTAL_DOWN = site({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
  available: false,
  unavailableReason: "TimeoutError",
});

function draw(siteId: string, rows: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, rows);
  return render(
    <Wrapper>
      <SiteAvailabilityGate siteId={siteId}>
        <div data-testid="app-shell" />
      </SiteAvailabilityGate>
    </Wrapper>,
  );
}

afterEach(() => {
  cleanup();
  useSessionStore.setState({ selectedSite: "veupathdb" });
});

describe("SiteAvailabilityGate", () => {
  it("renders the app for a site that answers", () => {
    draw("plasmodb", [PORTAL_DOWN, site({ id: "plasmodb" })]);

    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });

  it("replaces the app with the notice for a site that does not answer", () => {
    draw("veupathdb", [PORTAL_DOWN, site({ id: "plasmodb" })]);

    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
    expect(screen.getByTestId("site-unavailable-notice")).toBeInTheDocument();
    expect(
      screen.getByText("VEuPathDB Portal (All organisms) is not responding"),
    ).toBeInTheDocument();
  });

  it("leaves the stored site selection alone on a deep link to a site that is down", () => {
    useSessionStore.setState({ selectedSite: "plasmodb" });

    draw("veupathdb", [PORTAL_DOWN, site({ id: "plasmodb" })]);

    expect(useSessionStore.getState().selectedSite).toBe("plasmodb");
  });

  it("renders the app for a site the list does not name", () => {
    draw("orthomcl", [PORTAL_DOWN, site({ id: "plasmodb" })]);

    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });
});
