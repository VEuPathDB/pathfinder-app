// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { CombineMismatchGroup } from "@/features/strategy/graph";
import { ValidationAlert } from "./ValidationAlert";

const GROUPS: CombineMismatchGroup[] = [
  {
    id: "g1",
    ids: new Set(["step_a", "step_b"]),
    message: "record type mismatch",
  },
];

describe("ValidationAlert", () => {
  afterEach(() => cleanup());

  it("returns null when no combine mixes record types", () => {
    const { container } = render(
      <ValidationAlert mismatchGroups={[]} onView={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders count + View button when mismatchGroups present", () => {
    render(<ValidationAlert mismatchGroups={GROUPS} onView={vi.fn()} />);
    expect(screen.getByText("2 steps have mismatched record types.")).toBeVisible();
    expect(
      screen.getByText(
        "VEuPathDB combines only steps that return the same record type.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/paused/i)).toBeNull();
    expect(screen.getByRole("button", { name: /view/i })).toBeTruthy();
  });

  it("View button fires onView with first offending id", () => {
    const onView = vi.fn();
    render(<ValidationAlert mismatchGroups={GROUPS} onView={onView} />);
    fireEvent.click(screen.getByRole("button", { name: /view/i }));
    expect(onView).toHaveBeenCalledTimes(1);
    expect(["step_a", "step_b"]).toContain(onView.mock.calls[0]?.[0]);
  });
});
