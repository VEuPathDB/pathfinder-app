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

const PORTAL_DOWN: SiteResponse = {
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  baseUrl: "https://veupathdb.org/veupathdb",
  projectId: "EuPathDB",
  isPortal: true,
  available: false,
  unavailableReason: "TimeoutError",
};

function draw(down: boolean) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, [PORTAL_DOWN]);
  return render(
    <Wrapper>
      <SiteAvailabilityGate siteId="veupathdb" down={down}>
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
  it("renders the content for a site that is up", () => {
    draw(false);

    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });

  it("replaces the content with the notice for a site that is down", () => {
    draw(true);

    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
    expect(
      screen.getByText("Couldn't reach VEuPathDB Portal (All organisms)"),
    ).toBeInTheDocument();
  });

  it("leaves the stored site selection alone on a site that is down", () => {
    useSessionStore.setState({ selectedSite: "plasmodb" });

    draw(true);

    expect(useSessionStore.getState().selectedSite).toBe("plasmodb");
  });
});
