// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { AnimatedCount } from "./AnimatedCount";

function reduceMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as typeof window.matchMedia;
}

afterEach(() => cleanup());

describe("AnimatedCount", () => {
  it("renders the value with its digit separators", () => {
    reduceMotion(false);
    render(<AnimatedCount value={47668} />);
    expect(screen.getByTestId("animated-count").textContent).toBe("47,668");
  });

  it("shows a changed value at once under reduced motion", () => {
    reduceMotion(true);
    const { rerender } = render(<AnimatedCount value={45} />);
    rerender(<AnimatedCount value={440} />);
    expect(screen.getByTestId("animated-count").textContent).toBe("440");
  });
});
