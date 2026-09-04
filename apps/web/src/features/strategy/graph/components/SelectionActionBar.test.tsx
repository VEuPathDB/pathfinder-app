// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SelectionActionBar } from "./SelectionActionBar";

describe("SelectionActionBar", () => {
  afterEach(() => {
    cleanup();
  });

  it("is hidden when no selection", () => {
    const { container } = render(
      <SelectionActionBar selectedCount={0} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("is visible when selectedCount > 0", () => {
    render(
      <SelectionActionBar selectedCount={1} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    expect(screen.getByTestId("selection-action-bar")).toBeTruthy();
  });

  it("disables Combine when fewer than 2 selected", () => {
    render(
      <SelectionActionBar selectedCount={1} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    const combine = screen.getByRole("button", { name: /combine/i });
    expect(combine.getAttribute("aria-disabled")).toBe("true");
  });

  it("disables Ortholog when not exactly 1 selected", () => {
    render(
      <SelectionActionBar selectedCount={2} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    const ortholog = screen.getByRole("button", { name: /ortholog/i });
    expect(ortholog.getAttribute("aria-disabled")).toBe("true");
  });

  it("enables Combine with 2 selected and Ortholog with exactly 1", () => {
    const { rerender } = render(
      <SelectionActionBar selectedCount={2} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /combine/i }).getAttribute("aria-disabled"),
    ).toBe("false");

    rerender(
      <SelectionActionBar selectedCount={1} onCombine={vi.fn()} onOrtholog={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /ortholog/i }).getAttribute("aria-disabled"),
    ).toBe("false");
  });
});
