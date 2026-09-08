/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { http } from "msw";
import type { ReactNode } from "react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/veupathdb/conversation/c1",
  useRouter: () => ({ push: vi.fn() }),
}));

import { server } from "../../../vitest.msw-setup";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { chatUrl } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";
import { ChatThread } from "./ChatThread";
import { ChatHelpersProvider, type ChatHelpers } from "./runtime/chatHelpersContext";

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

function StubRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={STUB_CHAT}>{children}</ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}

function renderSignedInThread(conversationId: string) {
  server.use(http.post("http://localhost:3000/api/v1/chat", () => new Response(null)));

  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn: true },
  );

  render(
    <StubRuntimeProvider>
      <ChatThread conversationId={conversationId} />
    </StubRuntimeProvider>,
    { wrapper: Wrapper },
  );
}

describe("ChatThread", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("renders the thread root and composer with a textarea + send button", () => {
    renderSignedInThread("c1");

    expect(screen.getByPlaceholderText(/ask about strategies/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("pins the scroll control above the composer, outside the scrolling thread", () => {
    renderSignedInThread("c1");

    const viewport = screen.getByRole("log");
    const control = screen.getByRole("button", {
      name: "Scroll to the latest message",
    });
    expect(viewport.className).toContain("overflow-y-auto");
    expect(viewport.contains(control)).toBe(false);
    expect(screen.getByTestId("conversation-scroll-rail").contains(control)).toBe(true);
  });

  it("replaces the url with the conversation's chat url when a run starts", async () => {
    renderSignedInThread("c1");
    expect(window.location.pathname).toBe("/");

    fireEvent.change(screen.getByPlaceholderText(/ask about strategies/i), {
      target: { value: "list kinases" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(window.location.pathname).toBe(
        chatUrl(useSessionStore.getState().selectedSite, "c1"),
      );
    });
  });
});
