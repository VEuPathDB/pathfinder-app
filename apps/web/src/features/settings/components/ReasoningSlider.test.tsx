// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReasoningSlider } from "./ReasoningSlider";

afterEach(cleanup);

describe("ReasoningSlider", () => {
  it("runs from low to max and names the effort it holds", () => {
    render(<ReasoningSlider value="high" onChange={vi.fn()} />);

    const slider = screen.getByRole("slider", { name: "Reasoning effort" });
    expect(slider).toHaveAttribute("aria-valuemin", "0");
    expect(slider).toHaveAttribute("aria-valuemax", "4");
    expect(slider).toHaveAttribute("aria-valuenow", "2");
    expect(slider).toHaveAttribute("aria-valuetext", "High");
    expect(screen.getByText("High")).toBeVisible();
  });

  it("sets the top effort from the keyboard", () => {
    const onChange = vi.fn();
    render(<ReasoningSlider value="medium" onChange={onChange} />);

    fireEvent.keyDown(screen.getByRole("slider", { name: "Reasoning effort" }), {
      key: "End",
    });

    expect(onChange).toHaveBeenCalledWith("max");
  });

  it("sets the next effort down with an arrow key", () => {
    const onChange = vi.fn();
    render(<ReasoningSlider value="medium" onChange={onChange} />);

    fireEvent.keyDown(screen.getByRole("slider", { name: "Reasoning effort" }), {
      key: "ArrowLeft",
    });

    expect(onChange).toHaveBeenCalledWith("low");
  });
});
