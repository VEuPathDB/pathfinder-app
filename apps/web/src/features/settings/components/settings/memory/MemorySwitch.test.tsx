// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/features/settings/api/memories", () => ({
  getMemorySetting: vi.fn(),
  putMemorySetting: vi.fn(),
}));

import { getMemorySetting, putMemorySetting } from "@/features/settings/api/memories";
import { createTestWrapper } from "@/lib/query/testing";

import { MemorySwitch } from "./MemorySwitch";

const mockedGet = vi.mocked(getMemorySetting);
const mockedPut = vi.mocked(putMemorySetting);
const LABEL = "Use memory in my conversations";

function shown() {
  const { Wrapper } = createTestWrapper();
  render(<MemorySwitch />, { wrapper: Wrapper });
}

describe("MemorySwitch", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockedPut.mockReset();
  });

  it("shows memory on for a researcher who left it on", async () => {
    mockedGet.mockResolvedValue({ enabled: true });

    shown();

    expect(await screen.findByRole("switch", { name: LABEL })).toBeChecked();
  });

  it("turns memory off and shows the stored answer", async () => {
    const user = userEvent.setup();
    mockedGet.mockResolvedValue({ enabled: true });
    mockedPut.mockResolvedValue({ enabled: false });

    shown();
    await user.click(await screen.findByRole("switch", { name: LABEL }));

    expect(mockedPut).toHaveBeenCalledWith({ enabled: false });
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: LABEL })).not.toBeChecked(),
    );
  });

  it("says that stored memories stay while it is off", async () => {
    mockedGet.mockResolvedValue({ enabled: false });

    shown();

    expect(await screen.findByTestId("memory-switch-copy")).toHaveTextContent(
      "When this is off, PathFinder neither recalls nor saves memories in your conversations. The memories below stay until you turn it back on.",
    );
  });
});
