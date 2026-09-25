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
import BareConversationPage from "./conversation/page";

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
const PORTAL_DOWN = { ...PORTAL, available: false, unavailableReason: "TimeoutError" };

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

describe("site-less entry points", () => {
  it("sends a site-less conversation path to the portal's chat when it answers", async () => {
    answerWith([PORTAL, site({ id: "toxodb" })]);

    await BareConversationPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("veupathdb")]]);
  });

  it("sends a site-less conversation path to the first available site instead", async () => {
    answerWith([PORTAL_DOWN, site({ id: "toxodb" }), site({ id: "plasmodb" })]);

    await BareConversationPage();

    expect(redirectMock.mock.calls).toEqual([["/toxodb/conversation"]]);
  });

  it("shows the not-ready screen instead of redirecting when no site answers", async () => {
    answerWith([
      PORTAL_DOWN,
      site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
    ]);

    render(await BareConversationPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/no site is responding/i)).toBeInTheDocument();
    expect(screen.getByText(/veupathdb, toxodb/)).toBeInTheDocument();
  });

  it("shows the unreachable screen instead of redirecting when the sites request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    render(await BareConversationPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can't reach the server/i)).toBeInTheDocument();
  });
});
