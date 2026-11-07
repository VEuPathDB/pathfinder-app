/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/accountReads", () => ({
  allowInThisConversation: vi.fn(async () => ({ allowed: true })),
  setAlwaysAllowed: vi.fn(async () => ({ always: true })),
}));

import { allowInThisConversation, setAlwaysAllowed } from "@/lib/api/accountReads";

import { AccountReadCard } from "./AccountReadCard";

const WHAT = "Your other conversations about gametocyte kinases";

function asked(onAnswer = vi.fn()) {
  render(<AccountReadCard conversationId="conv-1" what={WHAT} onAnswer={onAnswer} />);
  return onAnswer;
}

describe("AccountReadCard", () => {
  beforeEach(() => {
    vi.mocked(allowInThisConversation).mockClear();
    vi.mocked(setAlwaysAllowed).mockClear();
  });

  it("says what Explore asks to read", () => {
    asked();

    expect(screen.getByTestId("account-read-what")).toHaveTextContent(WHAT);
  });

  it("allows one read when no box is ticked", async () => {
    const user = userEvent.setup();
    const onAnswer = asked();

    await user.click(screen.getByRole("button", { name: "Allow" }));

    expect(onAnswer).toHaveBeenCalledWith(true);
    expect(vi.mocked(allowInThisConversation).mock.calls).toHaveLength(0);
    expect(vi.mocked(setAlwaysAllowed).mock.calls).toHaveLength(0);
  });

  it("keeps the allowance for this conversation when its box is ticked", async () => {
    const user = userEvent.setup();
    const onAnswer = asked();

    await user.click(
      screen.getByRole("checkbox", { name: "Always allow in this conversation" }),
    );
    await user.click(screen.getByRole("button", { name: "Allow" }));

    expect(allowInThisConversation).toHaveBeenCalledWith("conv-1");
    expect(onAnswer).toHaveBeenCalledWith(true);
  });

  it("keeps the allowance for every conversation when its box is ticked", async () => {
    const user = userEvent.setup();
    asked();

    await user.click(
      screen.getByRole("checkbox", { name: "Always allow in all conversations" }),
    );
    await user.click(screen.getByRole("button", { name: "Allow" }));

    expect(setAlwaysAllowed).toHaveBeenCalledWith(true);
  });

  it("stores nothing when it is not allowed", async () => {
    const user = userEvent.setup();
    const onAnswer = asked();

    await user.click(
      screen.getByRole("checkbox", { name: "Always allow in all conversations" }),
    );
    await user.click(screen.getByRole("button", { name: "Don't allow" }));

    expect(onAnswer).toHaveBeenCalledWith(false);
    expect(vi.mocked(setAlwaysAllowed).mock.calls).toHaveLength(0);
  });
});
