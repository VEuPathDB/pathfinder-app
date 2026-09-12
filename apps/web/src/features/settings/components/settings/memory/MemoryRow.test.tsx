// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { MemoryItem } from "@pathfinder/shared";
import { MemoryRow } from "./MemoryRow";

afterEach(() => {
  cleanup();
});

const memItem: MemoryItem = {
  key: "k",
  value: {
    kind: "gene_set_note",
    name: "drug_targets",
    summary: "Validated targets",
    tags: ["plasmodb", "phase2"],
    content: {},
    autoRetrieve: true,
    createdAt: new Date().toISOString(),
  },
};

describe("MemoryRow", () => {
  it("renders name, summary, tags", () => {
    render(
      <MemoryRow
        item={memItem}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    expect(screen.getByText("drug_targets")).toBeInTheDocument();
    expect(screen.getByText("Validated targets")).toBeInTheDocument();
    expect(screen.getByText(/plasmodb/)).toBeInTheDocument();
  });

  it("fires onEdit when body is clicked", () => {
    const onEdit = vi.fn();
    render(
      <MemoryRow
        item={memItem}
        onEdit={onEdit}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("memory-row-body"));
    expect(onEdit).toHaveBeenCalledWith(memItem);
  });

  it("fires onDelete when delete is clicked", () => {
    const onDelete = vi.fn();
    render(
      <MemoryRow
        item={memItem}
        onEdit={vi.fn()}
        onDelete={onDelete}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText(/delete drug_targets/i));
    expect(onDelete).toHaveBeenCalledWith(memItem);
  });

  it("toggles auto-retrieve with new value", () => {
    const onToggle = vi.fn();
    render(
      <MemoryRow
        item={memItem}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={onToggle}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onToggle).toHaveBeenCalledWith(memItem, false);
  });

  it("reflects the current auto-retrieve value on the checkbox", () => {
    const offItem: MemoryItem = {
      ...memItem,
      value: { ...memItem.value, autoRetrieve: false },
    };
    render(
      <MemoryRow
        item={offItem}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleAutoRetrieve={vi.fn()}
      />,
    );
    const checkbox = screen.getByRole<HTMLInputElement>("checkbox");
    expect(checkbox.checked).toBe(false);
  });
});
