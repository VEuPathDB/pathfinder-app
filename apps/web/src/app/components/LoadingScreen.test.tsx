/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

const reloadPage = vi.hoisted(() => vi.fn());
vi.mock("./reloadPage", () => ({ reloadPage }));

import { LoadingScreen } from "./LoadingScreen";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LoadingScreen", () => {
  it("offers no reload inside the first 20 s", () => {
    render(<LoadingScreen />);

    act(() => {
      vi.advanceTimersByTime(19_999);
    });

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reload" })).not.toBeInTheDocument();
  });

  it("offers a reload after 20 s that reloads the page", () => {
    render(<LoadingScreen />);

    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    expect(reloadPage).toHaveBeenCalledTimes(1);
  });
});
