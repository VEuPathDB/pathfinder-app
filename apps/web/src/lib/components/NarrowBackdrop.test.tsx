/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { NarrowBackdrop } from "./NarrowBackdrop";

describe("NarrowBackdrop", () => {
  it("closes the panel it covers for", () => {
    const onClose = vi.fn();
    render(<NarrowBackdrop label="Close conversations" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close conversations" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows only below the width that holds a side panel", () => {
    render(<NarrowBackdrop label="Close panel" onClose={() => {}} />);

    expect(screen.getByRole("button", { name: "Close panel" })).toHaveClass(
      "min-[900px]:hidden",
    );
  });
});
