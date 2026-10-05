// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReasoningToggle } from "./ReasoningToggle";

afterEach(cleanup);

describe("ReasoningToggle", () => {
  it("offers every effort the models take, from low to max", () => {
    render(<ReasoningToggle value="medium" onChange={vi.fn()} />);

    expect(screen.getAllByRole("radio").map((radio) => radio.textContent)).toEqual([
      "Low",
      "Medium",
      "High",
      "Extra high",
      "Max",
    ]);
  });

  it("sets the top effort", () => {
    const onChange = vi.fn();
    render(<ReasoningToggle value="medium" onChange={onChange} />);

    fireEvent.click(screen.getByRole("radio", { name: "Max" }));

    expect(onChange).toHaveBeenCalledWith("max");
  });
});
