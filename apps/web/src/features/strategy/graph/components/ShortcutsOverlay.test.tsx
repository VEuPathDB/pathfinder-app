// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ShortcutsOverlay } from "./ShortcutsOverlay";

describe("ShortcutsOverlay", () => {
  afterEach(() => cleanup());

  it("renders shortcut sections when open", () => {
    render(<ShortcutsOverlay open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText("Keyboard shortcuts")).toBeInTheDocument();
    expect(screen.getByText("Canvas")).toBeInTheDocument();
    expect(screen.getByText("Selection")).toBeInTheDocument();
    expect(screen.getByText("Navigation")).toBeInTheDocument();
    expect(screen.getByText("Tidy layout")).toBeInTheDocument();
    expect(screen.getByText("Quick switcher")).toBeInTheDocument();
  });

  it("does not render content when closed", () => {
    render(<ShortcutsOverlay open={false} onOpenChange={vi.fn()} />);
    expect(screen.queryAllByRole("dialog")).toHaveLength(0);
    expect(screen.queryAllByText("Keyboard shortcuts")).toHaveLength(0);
  });
});
