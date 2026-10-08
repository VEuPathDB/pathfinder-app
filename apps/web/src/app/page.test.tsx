/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";
import type { SystemConfigResponse } from "@pathfinder/shared/generated/types/SystemConfigResponse";

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

function config(siteId: string): SystemConfigResponse {
  return {
    chatProvider: "openai",
    llmConfigured: true,
    providers: { openai: true, anthropic: false, google: false, ollama: false },
    siteId,
    siteSignInUrl: "https://veupathdb.org/veupathdb/app/user/login",
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function answerWith(rows: SiteResponse[], defaultSiteId: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.includes("/health/config") ? json(config(defaultSiteId)) : json(rows),
    ),
  );
}

afterEach(() => {
  cleanup();
  redirectMock.mockReset();
  vi.unstubAllGlobals();
});

describe("RootPage", () => {
  it("sends the bare root to the deployment's site when it answers", async () => {
    answerWith([PORTAL, site({ id: "plasmodb" })], "plasmodb");

    await RootPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("plasmodb")]]);
    expect(redirectMock).toHaveBeenCalledWith("/plasmodb/conversation");
  });

  it("sends the bare root to the portal's chat when the deployment's site is degraded", async () => {
    answerWith(
      [
        PORTAL,
        site({ id: "plasmodb", available: false, unavailableReason: "TimeoutError" }),
      ],
      "plasmodb",
    );

    await RootPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("veupathdb")]]);
  });

  it("sends the bare root to the first available site when the portal is degraded", async () => {
    answerWith(
      [
        { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
        site({ id: "toxodb" }),
        site({ id: "plasmodb" }),
      ],
      "veupathdb",
    );

    await RootPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("toxodb")]]);
  });

  it("shows the not-ready screen naming every site instead of redirecting when none answers", async () => {
    answerWith(
      [
        { ...PORTAL, available: false, unavailableReason: "TimeoutError" },
        site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
      ],
      "veupathdb",
    );

    render(await RootPage());

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

    render(await RootPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can't reach the server/i)).toBeInTheDocument();
  });

  it("shows the unreachable screen instead of redirecting when the config request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/health/config")
          ? json({ detail: "Service Unavailable" }, 503)
          : json([PORTAL]),
      ),
    );

    render(await RootPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can't reach the server/i)).toBeInTheDocument();
  });
});
