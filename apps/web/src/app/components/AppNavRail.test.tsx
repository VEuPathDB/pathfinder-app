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

const route = { pathname: "/plasmodb/conversation/abc-123" };
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

function draw() {
  return render(
    <AppNavRail
      siteId="plasmodb"
      onSiteChange={() => undefined}
      onOpenSettings={() => undefined}
      onOpenModelSettings={() => undefined}
      onToggleSidebar={() => undefined}
      sidebarExpanded={false}
    />,
  );
}

function drawFor(siteId: string, onSiteChange: (id: string) => void = () => undefined) {
  return render(
    <AppNavRail
      siteId={siteId}
      onSiteChange={onSiteChange}
      onOpenSettings={() => undefined}
      onOpenModelSettings={() => undefined}
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
  route.pathname = "/plasmodb/conversation/abc-123";
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
    route.pathname = "/plasmodb/conversation/abc-123";
    draw();
    const chat = await screen.findByRole("link", { name: "Conversation" });
    expect(chat).toHaveAttribute("aria-current", "page");
    const click = fireEvent.click(chat);
    expect(click).toBe(false);
  });

  it("navigates to a section the reader is not in", async () => {
    route.pathname = "/plasmodb/conversation/abc-123";
    draw();
    const saved = await screen.findByRole("link", { name: "Saved strategies" });
    expect(saved).not.toHaveAttribute("aria-current");
    const click = fireEvent.click(saved);
    expect(click).toBe(true);
  });

  it("links the chat, the saved strategies and help, and no workbench", async () => {
    draw();
    await screen.findByRole("link", { name: "Conversation" });
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/plasmodb/conversation", "/plasmodb/saved", "/help"]);
  });

  it("closes the bottom group with help, after the settings", async () => {
    draw();
    const help = await screen.findByRole("link", { name: "Help" });
    const settings = screen.getByRole("button", { name: "Settings" });

    expect(help).toHaveAttribute("href", "/help");
    expect(help.parentElement).toBe(settings.parentElement);
    expect(help.parentElement?.lastElementChild).toBe(help);
  });
});

describe("AppNavRail logo and spending meter", () => {
  it("opens the rail with the PathFinder logo, which is neither a link nor a button", async () => {
    draw();
    const logo = await screen.findByRole("img", { name: "PathFinder" });
    const rail = logo.parentElement;

    expect(rail?.firstElementChild).toBe(logo);
    expect(rail).toContainElement(screen.getByRole("link", { name: "Conversation" }));
    expect(screen.queryByRole("link", { name: "PathFinder" })).toBeNull();
    expect(screen.queryByRole("button", { name: "PathFinder" })).toBeNull();
    expect(logo.querySelector("img")).toHaveAttribute(
      "src",
      "/pathfinder/pathfinder.svg",
    );
  });

  it("names the logo PathFinder on hover", async () => {
    draw();
    await userEvent.hover(await screen.findByRole("img", { name: "PathFinder" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("PathFinder");
  });

  it("opens the bottom group with the spending meter, before the AI model settings", async () => {
    draw();
    const meter = await screen.findByRole("img", { name: "Monthly spend" });
    const model = screen.getByRole("button", { name: "AI model settings" });

    expect(meter.parentElement).toBe(model.parentElement);
    expect(meter.parentElement?.firstElementChild).toBe(meter);
    expect(
      meter.compareDocumentPosition(model) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
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
