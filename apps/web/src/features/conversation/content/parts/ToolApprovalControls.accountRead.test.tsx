/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/accountReads", () => ({
  allowInThisConversation: vi.fn(async () => ({ allowed: true })),
  setAlwaysAllowed: vi.fn(async () => ({ always: true })),
}));
vi.mock("@/lib/api/productEvents", () => ({ recordProductEvent: vi.fn() }));

import { allowInThisConversation } from "@/lib/api/accountReads";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { chatHelpersFor } from "./threadFixture";
import { ToolApprovalCard } from "./ToolApprovalControls";

const WHAT = "Your saved strategies on PlasmoDB";

function asked(respond = vi.fn()) {
  const messages: UIMessage[] = [
    {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-ask_to_read_the_account",
          toolCallId: "call-1",
          state: "approval-requested",
          input: { what: WHAT },
          approval: { id: "appr-1" },
        },
      ],
    },
  ];
  render(
    <ChatHelpersProvider
      value={{ ...chatHelpersFor(messages), addToolApprovalResponse: respond }}
    >
      <ToolApprovalCard toolCallId="call-1" />
    </ChatHelpersProvider>,
  );
  return respond;
}

describe("the account read ask", () => {
  it("is drawn as the account card with what Explore asks to read", () => {
    asked();

    expect(screen.getByTestId("account-read-what")).toHaveTextContent(WHAT);
  });

  it("keeps the allowance for the thread, then approves", async () => {
    const user = userEvent.setup();
    const respond = asked();

    await user.click(
      screen.getByRole("checkbox", { name: "Always allow in this conversation" }),
    );
    await user.click(screen.getByRole("button", { name: "Allow" }));

    await waitFor(() =>
      expect(respond).toHaveBeenCalledWith({ id: "appr-1", approved: true }),
    );
    expect(allowInThisConversation).toHaveBeenCalledWith("conv-1");
  });
});
