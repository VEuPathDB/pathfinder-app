/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const recordProductEvent = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation/conv-7",
}));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (state: { message: { id: string } }) => unknown) =>
    select({ message: { id: "msg-9" } }),
}));

vi.mock("@/lib/api/productEvents", () => ({ recordProductEvent }));

import { RegenerateAction } from "./RegenerateAction";

describe("RegenerateAction", () => {
  it("records assistant_regenerated for the message and still calls onClick", () => {
    const onClick = vi.fn();
    render(<RegenerateAction onClick={onClick} />);

    fireEvent.click(screen.getByRole("button"));

    expect(recordProductEvent).toHaveBeenCalledWith({
      event: "assistant_regenerated",
      messageId: "msg-9",
      conversationId: "conv-7",
    });
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
