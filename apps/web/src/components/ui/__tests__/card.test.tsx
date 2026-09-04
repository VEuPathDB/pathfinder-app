/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Card } from "@/components/ui/card";

describe("Card", () => {
  it("renders a bordered surface that adds no layout of its own", () => {
    render(<Card>body</Card>);
    const card = document.querySelector('[data-slot="card"]');
    expect(card).toHaveClass("rounded-lg", "border", "bg-card", "text-card-foreground");
    expect(card?.className).not.toContain("flex");
    expect(card?.className).not.toContain("gap-");
    expect(card?.className).not.toContain("py-");
  });

  it("keeps the caller's padding", () => {
    render(<Card className="px-4 py-3">body</Card>);
    const card = document.querySelector('[data-slot="card"]');
    expect(card).toHaveClass("px-4", "py-3");
  });
});
