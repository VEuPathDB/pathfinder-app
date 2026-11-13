// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/accountReads", () => ({
  ALWAYS_ACCOUNT_READS_KEY: ["me", "account-reads"],
  getAlwaysAllowed: vi.fn(),
  setAlwaysAllowed: vi.fn(),
}));

import { getAlwaysAllowed, setAlwaysAllowed } from "@/lib/api/accountReads";
import { createTestWrapper } from "@/lib/query/testing";

import { AccountReadsSwitch } from "./AccountReadsSwitch";

const LABEL = "Always let Strategist read my account in every conversation";

function shown() {
  const { Wrapper } = createTestWrapper();
  render(<AccountReadsSwitch />, { wrapper: Wrapper });
}

describe("AccountReadsSwitch", () => {
  beforeEach(() => {
    vi.mocked(getAlwaysAllowed).mockReset();
    vi.mocked(setAlwaysAllowed).mockReset();
  });

  it("shows the allowance the account holds", async () => {
    vi.mocked(getAlwaysAllowed).mockResolvedValue({ always: true });

    shown();

    expect(await screen.findByRole("switch", { name: LABEL })).toBeChecked();
  });

  it("takes the allowance back", async () => {
    const user = userEvent.setup();
    vi.mocked(getAlwaysAllowed).mockResolvedValue({ always: true });
    vi.mocked(setAlwaysAllowed).mockResolvedValue({ always: false });

    shown();
    await user.click(await screen.findByRole("switch", { name: LABEL }));

    expect(setAlwaysAllowed).toHaveBeenCalledWith(false);
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: LABEL })).not.toBeChecked(),
    );
  });
});
