/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { SiteResponse } from "@pathfinder/shared";

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
    baseUrl: "https://plasmodb.org/plasmo/service",
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

beforeEach(() => {
  sites.list = [];
  route.pathname = "/plasmodb/conversation/abc-123";
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

  it("links the chat and the saved strategies, and no workbench", async () => {
    draw();
    await screen.findByRole("link", { name: "Conversation" });
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/plasmodb/conversation", "/plasmodb/saved"]);
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
