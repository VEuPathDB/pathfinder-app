// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { MemoryItem } from "@strategist/shared";
import { MemorySection } from "./MemorySection";

afterEach(() => {
  cleanup();
});

function makeItem(name: string): MemoryItem {
  return {
    key: `k-${name}`,
    value: {
      kind: "knowledge",
      name,
      summary: `summary for ${name}`,
      tags: [],
      content: {},
      autoRetrieve: true,
      createdAt: new Date().toISOString(),
    },
  };
}

describe("MemorySection", () => {
  it("renders title and count", () => {
    render(
      <MemorySection
        title="Knowledge"
        items={[makeItem("a"), makeItem("b")]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    expect(screen.getByText(/Knowledge/)).toBeInTheDocument();
    expect(screen.getByText(/^2$/)).toBeInTheDocument();
  });

  it("is collapsed by default and expands on click", () => {
    render(
      <MemorySection
        title="Knowledge"
        items={[makeItem("a")]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    expect(screen.queryByText("a")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/ }));
    expect(screen.getByText("a")).toBeInTheDocument();
  });

  it("shows an empty state when there are no items and expanded", () => {
    render(
      <MemorySection
        title="Strategies"
        items={[]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Strategies/ }));
    expect(screen.getByText(/no items/i)).toBeInTheDocument();
  });

  it("forwards row callbacks", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggle = vi.fn();
    const item = makeItem("a");
    render(
      <MemorySection
        title="Knowledge"
        items={[item]}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleAutoRetrieve={onToggle}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/ }));
    fireEvent.click(screen.getByTestId("memory-row-body"));
    expect(onEdit).toHaveBeenCalledWith(item);
  });
});
