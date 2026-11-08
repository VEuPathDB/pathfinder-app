/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversation/conv-1",
}));

import { useLeftSidebarStore } from "@/state/useRightRailStore";
import { usePhoneBarStore } from "@/state/usePhoneBarStore";
import { PhoneBar } from "./PhoneBar";

beforeEach(() => {
  useLeftSidebarStore.setState({ collapsed: true });
  usePhoneBarStore.setState({ slot: null });
});

describe("PhoneBar", () => {
  it("holds every way around PathFinder in one bar that scrolls sideways", () => {
    render(<PhoneBar onOpenSettings={() => {}} />);

    const bar = screen.getByRole("navigation", { name: "PathFinder" });
    expect(bar).toHaveClass("overflow-x-auto");
    expect(
      within(bar)
        .getAllByRole("link")
        .map((link) => link.getAttribute("aria-label")),
    ).toEqual(["Conversation", "Saved strategies", "Help"]);
  });

  it("opens the conversation list", async () => {
    render(<PhoneBar onOpenSettings={() => {}} />);

    await userEvent.click(
      screen.getByRole("button", { name: "Open conversation sidebar" }),
    );

    expect(useLeftSidebarStore.getState().collapsed).toBe(false);
  });

  it("opens Settings", async () => {
    const onOpenSettings = vi.fn();
    render(<PhoneBar onOpenSettings={onOpenSettings} />);

    await userEvent.click(screen.getByRole("button", { name: "Settings" }));

    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it("offers its slot to the buttons of the open conversation", () => {
    render(<PhoneBar onOpenSettings={() => {}} />);

    expect(usePhoneBarStore.getState().slot).toBe(screen.getByTestId("phone-bar-slot"));
  });
});
