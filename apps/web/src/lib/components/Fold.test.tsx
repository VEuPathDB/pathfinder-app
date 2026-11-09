// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Fold } from "./Fold";

afterEach(() => cleanup());

describe("Fold", () => {
  it("opens and closes its body", async () => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: true,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    })) as typeof window.matchMedia;
    render(
      <Fold title="Assistant's notes" meta="1">
        <p>One note</p>
      </Fold>,
    );
    const toggle = screen.getByRole("button", { name: /Assistant's notes/ });
    expect([
      toggle.getAttribute("aria-expanded"),
      screen.queryByText("One note"),
    ]).toEqual(["false", null]);

    await userEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("One note")).toBeInTheDocument();
  });
});
