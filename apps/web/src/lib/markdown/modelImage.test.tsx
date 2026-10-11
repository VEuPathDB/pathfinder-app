/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelImage } from "./modelImage";

describe("an image in model-written markdown", () => {
  it.each([
    "https://example.invalid/p.png?q=gene+list",
    "//example.invalid/p.png?q=gene+list",
    "http://example.invalid/p.png",
    "/pathfinder/api/v1/me",
    "data:image/png;base64,iVBORw0KGgo=",
  ])("does not load from %s and shows its alt text", (src) => {
    const { container } = render(<ModelImage src={src} alt="pathway figure" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("pathway figure")).toBeDefined();
  });
});
