/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { PathFinderLogo } from "./PathFinderLogo";

describe("PathFinderLogo", () => {
  it("shows the light mark in the light theme and the dark mark in the dark theme", () => {
    const { container } = render(<PathFinderLogo size={40} />);

    const [light, dark] = Array.from(container.querySelectorAll("img"));
    expect(light).toHaveAttribute("src", "/pathfinder/brand/pathfinder-mark-light.svg");
    expect(light).toHaveClass("dark:hidden");
    expect(dark).toHaveAttribute("src", "/pathfinder/brand/pathfinder-mark-dark.svg");
    expect(dark).toHaveClass("hidden", "dark:block");
    expect(light).toHaveAttribute("width", "40");
    expect(dark).toHaveAttribute("height", "40");
  });

  it("is hidden from assistive technology when it carries no label", () => {
    const { container } = render(<PathFinderLogo size={24} />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("is one named image when it carries a label", () => {
    render(<PathFinderLogo size={24} label="PathFinder" />);

    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "PathFinder" })).toBeVisible();
  });
});
