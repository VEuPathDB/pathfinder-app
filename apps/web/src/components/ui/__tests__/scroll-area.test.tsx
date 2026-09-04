/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ScrollArea } from "@/components/ui/scroll-area";

describe("ScrollArea", () => {
  it("renders its children inside a clipped viewport", () => {
    render(
      <ScrollArea className="h-10">
        <p>gene set</p>
      </ScrollArea>,
    );
    expect(screen.getByText("gene set")).toBeInTheDocument();
    const root = document.querySelector('[data-slot="scroll-area"]');
    expect(root).toHaveClass("relative", "overflow-hidden", "h-10");
  });
});
