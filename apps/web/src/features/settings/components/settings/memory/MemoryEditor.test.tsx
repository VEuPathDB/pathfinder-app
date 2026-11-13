// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { MemoryItem } from "@strategist/shared";
import { MemoryEditor } from "./MemoryEditor";

afterEach(() => {
  cleanup();
});

const item: MemoryItem = {
  key: "k1",
  value: {
    kind: "knowledge",
    name: "My note",
    summary: "A short summary",
    tags: ["tagA", "tagB"],
    content: { foo: 1 },
    autoRetrieve: true,
    createdAt: new Date().toISOString(),
  },
};

describe("MemoryEditor", () => {
  it("initializes inputs from item.value", () => {
    render(<MemoryEditor open item={item} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText(/name/i)).toHaveValue("My note");
    expect(screen.getByLabelText(/summary/i)).toHaveValue("A short summary");
    expect(screen.getByLabelText(/tags/i)).toHaveValue("tagA, tagB");
    expect(screen.getByLabelText(/auto-retrieve/i)).toBeChecked();
  });

  it("disables Save when JSON content is invalid", () => {
    render(<MemoryEditor open item={item} onSave={vi.fn()} onCancel={vi.fn()} />);
    const textarea = screen.getByLabelText(/content/i);
    fireEvent.change(textarea, { target: { value: "not json {" } });
    const save = screen.getByRole("button", { name: /save/i });
    expect(save).toBeDisabled();
  });

  it("calls onSave with the edited MemoryEditRequest", () => {
    const onSave = vi.fn();
    render(<MemoryEditor open item={item} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/name/i), {
      target: { value: "Updated" },
    });
    fireEvent.change(screen.getByLabelText(/tags/i), {
      target: { value: "x, y" },
    });
    fireEvent.change(screen.getByLabelText(/content/i), {
      target: { value: '{"bar": 2}' },
    });
    fireEvent.click(screen.getByLabelText(/auto-retrieve/i));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSave).toHaveBeenCalledWith({
      name: "Updated",
      summary: "A short summary",
      tags: ["x", "y"],
      content: { bar: 2 },
      autoRetrieve: false,
    });
  });

  it("calls onCancel when cancel is clicked", () => {
    const onCancel = vi.fn();
    render(<MemoryEditor open item={item} onSave={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("does not render when open is false", () => {
    const { container } = render(
      <MemoryEditor open={false} item={item} onSave={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(container.textContent).toBe("");
  });
});
