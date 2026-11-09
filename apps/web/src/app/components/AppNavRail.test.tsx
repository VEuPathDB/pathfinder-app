/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";

import { server } from "../../../vitest.msw-setup";

const route = { pathname: "/conversation/abc-123" };
vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
}));

import { AppNavRail } from "./AppNavRail";

const openSettings = vi.fn();

function draw(offersAudits = true) {
  return render(
    <AppNavRail
      siteId="plasmodb"
      offersAudits={offersAudits}
      onToggleSidebar={() => undefined}
      sidebarExpanded={false}
      onOpenSettings={openSettings}
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

  it("links the chat, the saved strategies, the audits and help, and no workbench", async () => {
    draw();
    await screen.findByRole("link", { name: "Conversation" });
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/conversation", "/saved", "/audits", "/help"]);
  });

  it("offers no audits link on a site that offers no audit", async () => {
    draw(false);
    await screen.findByRole("link", { name: "Conversation" });
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/conversation", "/saved", "/help"]);
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

  it("never shows a site control", async () => {
    draw();
    await screen.findByRole("img", { name: "Monthly spend" });

    expect(
      screen.getAllByRole("button").map((button) => button.getAttribute("aria-label")),
    ).toEqual(["Open conversation sidebar", "Settings"]);
    expect(screen.queryByRole("menu")).toBe(null);
  });

  it("opens Settings from the gear beside Help", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: "Settings" }));

    expect(openSettings).toHaveBeenCalledTimes(1);
  });
});

describe("AppNavRail spending meter", () => {
  it("opens the rail with the sidebar toggle and ends it with the PathFinder mark", async () => {
    draw();

    const toggle = await screen.findByRole("button", {
      name: "Open conversation sidebar",
    });
    expect(toggle.parentElement?.firstElementChild).toBe(toggle);
    expect(screen.getByRole("img", { name: "PathFinder" })).toBeInTheDocument();
  });

  it("opens the bottom group with the spending meter", async () => {
    draw();
    const meter = await screen.findByRole("img", { name: "Monthly spend" });

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
