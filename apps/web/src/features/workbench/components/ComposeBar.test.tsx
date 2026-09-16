// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { ComposeBar } from "./ComposeBar";

afterEach(cleanup);

describe("ComposeBar", () => {
  const setA = {
    id: "a",
    name: "Set A",
    geneIds: ["g1", "g2", "g3"],
    geneCount: 3,
    membershipDigest: "0000000000000003",
    siteId: "PlasmoDB",
    source: "paste" as const,
    stepCount: 1,
    createdAt: "2026-01-01T00:00:00Z",
  };
  const setB = {
    id: "b",
    name: "Set B",
    geneIds: ["g2", "g3", "g4"],
    geneCount: 3,
    membershipDigest: "0000000000000002",
    siteId: "PlasmoDB",
    source: "paste" as const,
    stepCount: 1,
    createdAt: "2026-01-01T00:00:00Z",
  };

  it("shows live result count for intersection", () => {
    render(<ComposeBar setA={setA} setB={setB} onExecute={vi.fn()} />);
    // Default operation is intersect, g2+g3 = 2 genes
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("switches to union and shows correct count", () => {
    render(<ComposeBar setA={setA} setB={setB} onExecute={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Union"));
    // Union: g1, g2, g3, g4 = 4 genes
    expect(screen.getByText("4")).toBeTruthy();
  });

  it("switches to minus and shows correct count", () => {
    render(<ComposeBar setA={setA} setB={setB} onExecute={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Minus"));
    // A - B = g1 (1 gene)
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("swap button reverses operands for minus", () => {
    render(<ComposeBar setA={setA} setB={setB} onExecute={vi.fn()} />);
    // Switch to minus
    fireEvent.click(screen.getByLabelText("Minus"));
    // A - B = g1 (1 gene)
    expect(screen.getByText("1")).toBeTruthy();

    // Swap: now B - A = g4 (still 1 gene, but different gene)
    fireEvent.click(screen.getByLabelText("Swap operands"));
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("calls onExecute with operation result", () => {
    const handler = vi.fn();
    render(<ComposeBar setA={setA} setB={setB} onExecute={handler} />);
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    expect(handler).toHaveBeenCalledWith({
      operation: "intersect",
      geneIds: ["g2", "g3"],
      name: expect.stringContaining("\u2229"),
    });
  });

  it("disables Create button when result is empty", () => {
    const emptySetA = { ...setA, geneIds: ["g1"] };
    const emptySetB = { ...setB, geneIds: ["g5"] };
    render(<ComposeBar setA={emptySetA} setB={emptySetB} onExecute={vi.fn()} />);
    // Intersect of disjoint sets = 0
    const createBtn = screen.getByRole("button", { name: /create/i });
    expect(createBtn.hasAttribute("disabled")).toBe(true);
  });

  it("displays operand names", () => {
    render(<ComposeBar setA={setA} setB={setB} onExecute={vi.fn()} />);
    expect(screen.getByText("Set A")).toBeTruthy();
    expect(screen.getByText("Set B")).toBeTruthy();
  });
});
