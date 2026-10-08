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

describe("site-less entry points", () => {
  it("sends a site-less conversation path to the deployment's site when it answers", async () => {
    answerWith([PORTAL, site({ id: "toxodb" })], "toxodb");

    await BareConversationPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("toxodb")]]);
  });

  it("sends a site-less conversation path to the portal's chat when the deployment's site is degraded", async () => {
    answerWith(
      [
        PORTAL,
        site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
      ],
      "toxodb",
    );

    await BareConversationPage();

    expect(redirectMock.mock.calls).toEqual([[chatRoot("veupathdb")]]);
  });

  it("sends a site-less conversation path to the first available site instead", async () => {
    answerWith(
      [PORTAL_DOWN, site({ id: "toxodb" }), site({ id: "plasmodb" })],
      "veupathdb",
    );

    await BareConversationPage();

    expect(redirectMock.mock.calls).toEqual([["/toxodb/conversation"]]);
  });

  it("shows the not-ready screen instead of redirecting when no site answers", async () => {
    answerWith(
      [
        PORTAL_DOWN,
        site({ id: "toxodb", available: false, unavailableReason: "ConnectError" }),
      ],
      "veupathdb",
    );

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

  it("shows the unreachable screen instead of redirecting when the config request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/health/config")
          ? json({ detail: "Service Unavailable" }, 503)
          : json([PORTAL]),
      ),
    );

    render(await BareConversationPage());

    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can't reach the server/i)).toBeInTheDocument();
  });
});
