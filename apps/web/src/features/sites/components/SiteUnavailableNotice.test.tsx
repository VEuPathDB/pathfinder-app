/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";
import { chatRoot } from "@/lib/routes";
import { SiteUnavailableNotice } from "./SiteUnavailableNotice";

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
  unavailableReason: "the site did not answer in time",
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
  it("names the site, says what happened, and links every site that is available", () => {
    draw("veupathdb", [PORTAL_DOWN, site({ id: "toxodb", displayName: "ToxoDB" })]);

    expect(
      screen.getByText("Couldn't reach VEuPathDB Portal (All organisms)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "PathFinder cannot use this site right now: the site did not answer in time. It keeps trying every minute, so this may clear on its own.",
      ),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "ToxoDB" });
    expect(link.getAttribute("href")).toBe(chatRoot("toxodb"));
  });

  it("does not link the site that is down", () => {
    draw("veupathdb", [PORTAL_DOWN, site({ id: "toxodb", displayName: "ToxoDB" })]);

    expect(
      screen.queryByRole("link", { name: /VEuPathDB Portal/ }),
    ).not.toBeInTheDocument();
  });

  it("names the site id and offers no link when the site list is not loaded", () => {
    draw("veupathdb", undefined);

    expect(screen.getByText("Couldn't reach veupathdb")).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toEqual([]);
  });
});
