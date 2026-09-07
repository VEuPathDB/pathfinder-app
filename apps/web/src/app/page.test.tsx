/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

const redirectMock = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirectMock(url),
}));

import { chatRoot } from "@/lib/routes";
import RootPage from "./page";

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

const PORTAL = site({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
});

function answerWith(rows: SiteResponse[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(rows), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
}

afterEach(() => {
  cleanup();
  redirectMock.mockReset();
  vi.unstubAllGlobals();
});

describe("RootPage", () => {
  it("sends the bare root to the portal's chat when the portal answers", async () => {
    answerWith([PORTAL, site({ id: "toxodb" })]);

    await RootPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("veupathdb")]]);
    expect(redirectMock).toHaveBeenCalledWith("/veupathdb/conversation");
  });

  it("sends the bare root to the first available site when the portal is degraded", async () => {
    answerWith([
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb" }),
      site({ id: "plasmodb" }),
    ]);

    await RootPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("toxodb")]]);
  });

  it("shows the not-ready screen naming every site instead of redirecting when none answers", async () => {
    answerWith([
      { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
    ]);

    render(await RootPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/no database is responding/i)).toBeInTheDocument();
    expect(screen.getByText(/veupathdb, toxodb/)).toBeInTheDocument();
  });

  it("shows the unreachable screen instead of redirecting when the sites request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    render(await RootPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can't reach the server/i)).toBeInTheDocument();
  });
});
