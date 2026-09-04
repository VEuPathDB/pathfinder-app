/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Label } from "@/components/ui/label";

describe("Label", () => {
  it("binds to the control named by htmlFor", () => {
    render(
      <>
        <Label htmlFor="genes">Gene ids</Label>
        <input id="genes" />
      </>,
    );
    expect(screen.getByLabelText("Gene ids")).toBe(document.getElementById("genes"));
  });

  it("adds no display of its own so the caller controls the flow", () => {
    render(<Label>Parameter</Label>);
    const label = screen.getByText("Parameter");
    expect(label).toHaveClass("text-sm", "font-medium");
    expect(label.className).not.toContain("flex");
  });
});
