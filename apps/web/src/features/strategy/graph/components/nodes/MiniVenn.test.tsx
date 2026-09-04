// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { combineOpEnum } from "@pathfinder/shared";
import { MiniVenn } from "./MiniVenn";

describe("MiniVenn", () => {
  it("renders both circles filled for UNION", () => {
    const { container } = render(<MiniVenn operator={combineOpEnum.UNION} />);
    const left = container.querySelector('[data-region="left-only"]');
    const right = container.querySelector('[data-region="right-only"]');
    const lens = container.querySelector('[data-region="lens"]');
    expect(left?.getAttribute("data-active")).toBe("true");
    expect(right?.getAttribute("data-active")).toBe("true");
    expect(lens?.getAttribute("data-active")).toBe("true");
  });

  it("renders only the lens for INTERSECT", () => {
    const { container } = render(<MiniVenn operator={combineOpEnum.INTERSECT} />);
    const left = container.querySelector('[data-region="left-only"]');
    const right = container.querySelector('[data-region="right-only"]');
    const lens = container.querySelector('[data-region="lens"]');
    expect(left?.getAttribute("data-active")).toBe("false");
    expect(right?.getAttribute("data-active")).toBe("false");
    expect(lens?.getAttribute("data-active")).toBe("true");
  });

  it("renders left circle minus lens for MINUS", () => {
    const { container } = render(<MiniVenn operator={combineOpEnum.MINUS} />);
    const left = container.querySelector('[data-region="left-only"]');
    const right = container.querySelector('[data-region="right-only"]');
    const lens = container.querySelector('[data-region="lens"]');
    expect(left?.getAttribute("data-active")).toBe("true");
    expect(right?.getAttribute("data-active")).toBe("false");
    expect(lens?.getAttribute("data-active")).toBe("false");
  });

  it("renders right circle minus lens for RMINUS", () => {
    const { container } = render(<MiniVenn operator={combineOpEnum.RMINUS} />);
    const left = container.querySelector('[data-region="left-only"]');
    const right = container.querySelector('[data-region="right-only"]');
    const lens = container.querySelector('[data-region="lens"]');
    expect(left?.getAttribute("data-active")).toBe("false");
    expect(right?.getAttribute("data-active")).toBe("true");
    expect(lens?.getAttribute("data-active")).toBe("false");
  });

  it("falls back to separated circles + arrow for COLOCATE", () => {
    const { container } = render(<MiniVenn operator={combineOpEnum.COLOCATE} />);
    expect(screen.getByRole("img", { name: "colocate operator" })).toHaveAttribute(
      "data-mode",
      "colocate",
    );
    expect(container.querySelectorAll('[data-region="colocate-arrow"]')).toHaveLength(
      1,
    );
    expect(container.querySelectorAll('[data-region="lens"]')).toHaveLength(0);
  });
});
