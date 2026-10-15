/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PathFinderMark } from "./PathFinderMark";

describe("PathFinderMark", () => {
  it("shows the logo, which is neither a link nor a button", () => {
    render(<PathFinderMark />);

    const mark = screen.getByRole("img", { name: "PathFinder" });
    expect(mark.querySelector("img")).toHaveAttribute(
      "src",
      "/pathfinder/pathfinder.svg",
    );
    expect(screen.queryByRole("link", { name: "PathFinder" })).toBeNull();
    expect(screen.queryByRole("button", { name: "PathFinder" })).toBeNull();
  });

  it("names the product on hover", async () => {
    render(<PathFinderMark />);

    await userEvent.hover(screen.getByRole("img", { name: "PathFinder" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("PathFinder");
  });

  it("names the product on a touch tap", async () => {
    render(<PathFinderMark />);

    await userEvent.pointer({
      keys: "[TouchA]",
      target: screen.getByRole("img", { name: "PathFinder" }),
    });

    expect(await screen.findByRole("tooltip")).toHaveTextContent("PathFinder");
  });
});
