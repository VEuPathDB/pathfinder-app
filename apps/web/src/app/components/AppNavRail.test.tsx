/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { SiteResponse } from "@pathfinder/shared";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";

import { server } from "../../../vitest.msw-setup";

const route = { pathname: "/conversation/abc-123" };
const sites: { list: SiteResponse[] } = { list: [] };

vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api/sites", () => ({
  sitesOptions: () => ({
    queryKey: ["sites"],
    queryFn: () => sites.list,
  }),
}));

function site(over: Partial<SiteResponse>): SiteResponse {
  return {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://qa.plasmodb.org/plasmo.qa/service",
    projectId: "PlasmoDB",
    isPortal: false,
    siteOrigin: "https://qa.plasmodb.org",
    signInUrl: "https://qa.plasmodb.org/plasmo.qa/app/user/login",
    pageUrl: "https://qa.plasmodb.org/plasmo.qa/app/pathfinder",
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
  unavailableReason: "ReadTimeout",
});

const recordProductEvent = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/productEvents", () => ({ recordProductEvent }));

import { AppNavRail } from "./AppNavRail";

function draw(siteSwitchable = true) {
  return render(
    <AppNavRail
      siteId="plasmodb"
      siteSwitchable={siteSwitchable}
      onSiteChange={() => undefined}
      onToggleSidebar={() => undefined}
      sidebarExpanded={false}
    />,
  );
}

function drawFor(siteId: string, onSiteChange: (id: string) => void = () => undefined) {
  return render(
    <AppNavRail
      siteId={siteId}
      siteSwitchable
      onSiteChange={onSiteChange}
      onToggleSidebar={() => undefined}
      sidebarExpanded={false}
    />,
  );
}

const QUOTA: QuotaResponse = {
  usedUsd: "1.25",
  limitUsd: "10.00",
  totalTokens: 123456,
  percent: 12.5,
  resetsAt: "2026-10-01T12:00:00Z",
  ownKeyUsd: "0",
  ownKeyTokens: 0,
  ownKeyProviders: [],
};

beforeEach(() => {
  recordProductEvent.mockClear();
  sites.list = [];
  route.pathname = "/conversation/abc-123";
  server.use(
    http.get("http://localhost:3000/pathfinder/api/v1/veupathdb/auth/status", () =>
      HttpResponse.json({ signedIn: true }),
    ),
    http.get("http://localhost:3000/pathfinder/api/v1/me/quota", () =>
      HttpResponse.json(QUOTA),
    ),
  );
});

afterEach(cleanup);

describe("AppNavRail section links", () => {
  it("does nothing on the section the reader is already in", async () => {
    route.pathname = "/conversation/abc-123";
    draw();
    const chat = await screen.findByRole("link", { name: "Conversation" });
    expect(chat).toHaveAttribute("aria-current", "page");
    const click = fireEvent.click(chat);
    expect(click).toBe(false);
  });

  it("navigates to a section the reader is not in", async () => {
    route.pathname = "/conversation/abc-123";
    draw();
    const saved = await screen.findByRole("link", { name: "Saved strategies" });
    expect(saved).not.toHaveAttribute("aria-current");
    const click = fireEvent.click(saved);
    expect(click).toBe(true);
  });

  it("links the chat, the saved strategies and the audits, and neither help nor a workbench", async () => {
    draw();
    await screen.findByRole("link", { name: "Conversation" });
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/conversation", "/saved", "/audits"]);
  });

  it("names the audits link and marks it current on an audit page", async () => {
    route.pathname = "/audits/0a1b/findings/7";
    draw();
    const audits = await screen.findByRole("link", { name: "Audits" });
    expect(audits).toHaveAttribute("href", "/audits");
    expect(audits).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Conversation" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("offers no site switch on a website locked to its own site", async () => {
    draw(false);
    await screen.findByRole("img", { name: "Monthly spend" });

    expect(screen.queryByRole("button", { name: "Switch site" })).toBe(null);
  });

  it("carries no settings gear, which sits beside Help", async () => {
    draw();
    await screen.findByRole("img", { name: "Monthly spend" });

    expect(screen.queryAllByRole("button", { name: "Settings" })).toHaveLength(0);
  });
});

describe("AppNavRail spending meter", () => {
  it("opens the rail with the sidebar toggle and carries no logo", async () => {
    draw();

    const toggle = await screen.findByRole("button", {
      name: "Open conversation sidebar",
    });
    expect(toggle.parentElement?.firstElementChild).toBe(toggle);
    expect(screen.queryByRole("img", { name: "PathFinder" })).toBeNull();
  });

  it("opens the bottom group with the spending meter, before the site switch", async () => {
    draw();
    const meter = await screen.findByRole("img", { name: "Monthly spend" });
    const sites = await screen.findByRole("button", { name: "Switch site" });

    expect(meter.parentElement).toBe(sites.parentElement);
    expect(meter.parentElement?.firstElementChild).toBe(meter);
  });

  it("offers no model settings button of its own", async () => {
    draw();
    await screen.findByRole("img", { name: "Monthly spend" });

    expect(screen.queryAllByRole("button", { name: "AI model settings" })).toHaveLength(
      0,
    );
  });
});

describe("AppNavRail site selection", () => {
  it("marks a site PathFinder cannot reach, and keeps it selectable", async () => {
    sites.list = [site({}), PORTAL_DOWN];
    const picked = vi.fn();
    drawFor("plasmodb", picked);

    await userEvent.click(await screen.findByRole("button", { name: "Switch site" }));

    const down = await screen.findByTestId("site-menu-item-veupathdb");
    expect(down.getAttribute("aria-label")).toBe(
      "Couldn't reach VEuPathDB Portal (All organisms)",
    );
    expect(screen.getByTestId("site-degraded-veupathdb")).toHaveTextContent(
      "Couldn't reach",
    );

    await userEvent.click(down);
    expect(picked).toHaveBeenCalledWith("veupathdb");
  });

  it("records site_switched with both sites when another site is picked", async () => {
    sites.list = [
      site({}),
      site({ id: "toxodb", name: "ToxoDB", displayName: "ToxoDB" }),
    ];
    drawFor("plasmodb");

    await userEvent.click(await screen.findByRole("button", { name: "Switch site" }));
    await userEvent.click(await screen.findByTestId("site-menu-item-toxodb"));

    expect(recordProductEvent.mock.calls).toEqual([
      [
        {
          event: "site_switched",
          fromSite: "plasmodb",
          toSite: "toxodb",
          conversationId: "abc-123",
        },
      ],
    ]);
  });

  it("records nothing when the current site is picked again", async () => {
    sites.list = [site({})];
    drawFor("plasmodb");

    await userEvent.click(await screen.findByRole("button", { name: "Switch site" }));
    await userEvent.click(await screen.findByTestId("site-menu-item-plasmodb"));

    expect(recordProductEvent).not.toHaveBeenCalled();
  });

  it("leaves a site that answers unmarked", async () => {
    sites.list = [
      site({}),
      site({ ...PORTAL_DOWN, available: true, unavailableReason: null }),
    ];
    drawFor("plasmodb");

    await userEvent.click(await screen.findByRole("button", { name: "Switch site" }));

    const up = await screen.findByTestId("site-menu-item-veupathdb");
    expect(up.getAttribute("aria-label")).toBe("VEuPathDB Portal (All organisms)");
    expect(screen.queryByTestId("site-degraded-veupathdb")).toBeNull();
  });

  it("marks the trigger when the current site is the one that is down", async () => {
    sites.list = [site({}), PORTAL_DOWN];
    drawFor("veupathdb");

    const trigger = await screen.findByRole("button", {
      name: "Switch site",
    });
    expect(trigger.getAttribute("aria-label")).toBe("Switch site");
    expect(screen.getByLabelText("Couldn't reach VEuPathDB")).toBeInTheDocument();
    expect(trigger).toContainElement(screen.getByTestId("site-trigger-degraded"));
  });

  it("leaves the trigger unmarked when the current site answers", async () => {
    sites.list = [site({}), PORTAL_DOWN];
    drawFor("plasmodb");

    const trigger = await screen.findByRole("button", { name: "Switch site" });
    expect(trigger.getAttribute("aria-label")).toBe("Switch site");
    expect(screen.queryByTestId("site-trigger-degraded")).toBeNull();
  });
});
