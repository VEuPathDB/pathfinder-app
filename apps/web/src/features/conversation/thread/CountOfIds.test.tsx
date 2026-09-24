/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CountOfIds } from "./CountOfIds";

const IDS = ["PF3D7_1222600", "PF3D7_1031000"];

describe("CountOfIds", () => {
  it("reads the plain count when no id is known", () => {
    render(<CountOfIds count={3} ids={[]} noun="positive controls" />);

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByTestId("count-of-ids")).not.toBeInTheDocument();
  });

  it("names what the count stands for on the control that opens the ids", () => {
    render(<CountOfIds count={2} ids={IDS} noun="positive controls recovered" />);

    expect(
      screen.getByRole("button", {
        name: "2 positive controls recovered, click to copy the ids",
      }),
    ).toBeInTheDocument();
  });

  it("shows every id behind the count on hover", async () => {
    const user = userEvent.setup();
    render(<CountOfIds count={2} ids={IDS} noun="positive controls recovered" />);

    await user.hover(screen.getByTestId("count-of-ids"));

    await waitFor(() => {
      expect(screen.getByText("PF3D7_1222600, PF3D7_1031000")).toBeInTheDocument();
    });
    expect(screen.getByText("Click the number to copy them.")).toBeInTheDocument();
  });

  it("copies every id it holds when the count is clicked", () => {
    const written: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => void written.push(text) },
    });
    render(<CountOfIds count={2} ids={IDS} noun="positive controls recovered" />);

    fireEvent.click(screen.getByTestId("count-of-ids"));

    expect(written).toEqual(["PF3D7_1222600, PF3D7_1031000"]);
  });
});
