/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

const route = vi.hoisted(() => ({ pathname: "/conversation/conv-1" }));

vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
}));

import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

import { server } from "../../../../vitest.msw-setup";
import { ShareButton } from "./ShareButton";

function show(onPhone = false) {
  const { Wrapper } = createTestWrapper();
  return render(<ShareButton conversationId="conv-1" onPhone={onPhone} />, {
    wrapper: Wrapper,
  });
}

afterEach(() => {
  route.pathname = "/conversation/conv-1";
  useSessionStore.setState({ createdConversationId: null });
});

describe("ShareButton", () => {
  it("opens the share dialog", async () => {
    server.use(
      http.get(
        "http://localhost:3000/pathfinder/api/v1/conversations/conv-1/share",
        () => HttpResponse.json({ share: null }),
      ),
    );
    show();

    await userEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(
      await screen.findByRole("dialog", { name: "Share this conversation" }),
    ).toBeInTheDocument();
  });

  it("names itself on a phone, where it shows only its icon", () => {
    show(true);

    expect(screen.getByRole("button", { name: "Share" })).not.toHaveTextContent(
      "Share",
    );
  });

  it("is absent while the conversation is a draft with no row", () => {
    route.pathname = "/conversation";
    show();

    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
