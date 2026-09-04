/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Badge } from "@/components/ui/badge";

describe("Badge outcome variants", () => {
  it("tints a success badge from the success token", () => {
    render(<Badge variant="success">True Positive</Badge>);
    const badge = screen.getByText("True Positive");
    expect(badge).toHaveClass("bg-success/15");
    expect(badge).toHaveClass("text-success");
  });

  it("tints a warning badge from the warning token", () => {
    render(<Badge variant="warning">False Negative</Badge>);
    const badge = screen.getByText("False Negative");
    expect(badge).toHaveClass("bg-warning/15");
    expect(badge).toHaveClass("text-warning");
  });
});
