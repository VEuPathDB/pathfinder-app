/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createTestWrapper } from "@/lib/query/testing";

import { RailFoot } from "./RailFoot";

afterEach(cleanup);

function drawFoot(onOpenSettings: () => void) {
  const { Wrapper } = createTestWrapper();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  render(<RailFoot onOpenSettings={onOpenSettings} />, { wrapper: Wrapper });
}

describe("RailFoot", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("puts the settings gear right after help, then the mark", () => {
    drawFoot(() => undefined);

    const help = screen.getByRole("link", { name: "Help" });
    const gear = screen.getByRole("button", { name: "Settings" });
    expect(help).toHaveAttribute("href", "/help");
    expect(help.nextElementSibling).toBe(gear);
    expect(
      gear.nextElementSibling?.contains(
        screen.getByRole("img", { name: "PathFinder" }),
      ),
    ).toBe(true);
  });

  it("opens Settings from the gear, by keyboard too", async () => {
    const open = vi.fn();
    drawFoot(open);

    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    screen.getByRole("button", { name: "Settings" }).focus();
    await userEvent.keyboard("{Enter}");

    expect(open).toHaveBeenCalledTimes(2);
  });
});
