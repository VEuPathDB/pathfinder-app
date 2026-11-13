/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";
import { SiteUnavailableNotice } from "./SiteUnavailableNotice";

function site(over: Partial<SiteResponse>): SiteResponse {
  return {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://qa.plasmodb.org/plasmo.qa",
    projectId: "PlasmoDB",
    isPortal: false,
    siteOrigin: "https://qa.plasmodb.org",
    signInUrl: "https://qa.plasmodb.org/plasmo.qa/app/user/login",
    pageUrl: "https://qa.plasmodb.org/plasmo.qa/app/pathfinder",
    available: true,
    unavailableReason: null,
    offersAudits: false,
    ...over,
  };
}

const PORTAL_DOWN = site({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
  available: false,
  unavailableReason: "the site did not answer in time",
  offersAudits: false,
});

function draw(siteId: string, rows: SiteResponse[] | undefined) {
  const { queryClient, Wrapper } = createTestWrapper();
  if (rows !== undefined) {
    queryClient.setQueryData(sitesOptions().queryKey, rows);
  }
  return render(
    <Wrapper>
      <SiteUnavailableNotice siteId={siteId} />
    </Wrapper>,
  );
}

afterEach(cleanup);

describe("SiteUnavailableNotice", () => {
  it("names the site, says what happened, and offers no other site", () => {
    draw("veupathdb", [PORTAL_DOWN, site({ id: "toxodb", displayName: "ToxoDB" })]);

    expect(screen.getByText("Couldn't reach VEuPathDB")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Strategist cannot use this site right now: the site did not answer in time. It keeps trying every minute, so this may clear on its own.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toEqual([]);
  });

  it("names the site by its short name when the site list is not loaded", () => {
    draw("veupathdb", undefined);

    expect(screen.getByText("Couldn't reach VEuPathDB")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Strategist cannot use this site right now. It keeps trying every minute, so this may clear on its own.",
      ),
    ).toBeInTheDocument();
  });
});
