/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import type { ReactNode } from "react";
import type { UIMessage } from "ai";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => "/plasmodb/conversation",
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "@/features/conversation/runtime/chatHelpersContext";

import { Composer, stopClickBlocked } from "./Composer";

function StubRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

let runCalls = 0;

function CountingRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      runCalls += 1;
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

function HangingRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      await new Promise<void>(() => {});
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

function makeChat(messages: UIMessage[]): ChatHelpers {
  return {
    id: "test-conversation",
    messages,
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

function renderComposer(
  signedIn: boolean,
  options?: {
    hangingRuntime?: boolean;
    countingRuntime?: boolean;
    messages?: UIMessage[];
  },
) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn },
  );
  const Runtime =
    options?.hangingRuntime === true
      ? HangingRuntimeProvider
      : options?.countingRuntime === true
        ? CountingRuntimeProvider
        : StubRuntimeProvider;
  return render(
    <Runtime>
      <ChatHelpersProvider value={makeChat(options?.messages ?? [])}>
        <Composer conversationId="test-conversation" assistantId="pathfinder" />
      </ChatHelpersProvider>
    </Runtime>,
    { wrapper: Wrapper },
  );
}

function cancelCalls(fetchMock: ReturnType<typeof vi.fn>): unknown[] {
  return fetchMock.mock.calls.filter(
    (call) => typeof call[0] === "string" && call[0].includes("/cancel"),
  );
}

async function sendAndWaitForStop(): Promise<void> {
  fireEvent.change(screen.getByTestId("message-input"), {
    target: { value: "count the genes" },
  });
  fireEvent.click(screen.getByTestId("send-button"));
  await waitFor(() => expect(screen.getByTestId("stop-button")).toBeInTheDocument());
}

describe("Composer", () => {
  it("renders an input and send button for a signed-in user", () => {
    renderComposer(true);
    expect(screen.getByPlaceholderText(/ask about strategies/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
    expect(screen.queryByTestId("veupathdb-signin-required")).not.toBeInTheDocument();
  });

  it("disables the composer and asks for a VEuPathDB login when signed out", () => {
    renderComposer(false);
    expect(screen.getByTestId("veupathdb-signin-required")).toHaveTextContent(
      "Sign in to VEuPathDB to build strategies",
    );
    expect(
      screen.getByPlaceholderText("Sign in to VEuPathDB to build strategies"),
    ).toBeDisabled();
    expect(screen.getByTestId("send-button")).toBeDisabled();
  });
});

describe("stopClickBlocked", () => {
  it("blocks a stop click 1ms after a send", () => {
    expect(stopClickBlocked(1000, 1001)).toBe(true);
  });

  it("blocks a stop click 499ms after a send", () => {
    expect(stopClickBlocked(1000, 1499)).toBe(true);
  });

  it("allows a stop click exactly 500ms after a send", () => {
    expect(stopClickBlocked(1000, 1500)).toBe(false);
  });

  it("allows a stop click long after a send", () => {
    expect(stopClickBlocked(1000, 60_000)).toBe(false);
  });

  it("allows a stop click when this composer never sent", () => {
    expect(stopClickBlocked(0, 1_700_000_000_000)).toBe(false);
  });
});

describe("the second click of a double-click on Send does not cancel the turn", () => {
  it("ignores a Stop click inside the guard window", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    // The clock is frozen so the Stop click is inside the window by
    // construction, not by how fast the send rendered.
    let now = 1_700_000_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    renderComposer(true, { hangingRuntime: true });

    await sendAndWaitForStop();
    now += 499;
    fireEvent.click(screen.getByTestId("stop-button"));

    expect(cancelCalls(fetchMock)).toHaveLength(0);
  });

  it("cancels on a deliberate Stop click after the guard window", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    let now = 1_700_000_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    renderComposer(true, { hangingRuntime: true });

    await sendAndWaitForStop();
    now += 500;
    fireEvent.click(screen.getByTestId("stop-button"));

    expect(cancelCalls(fetchMock)).toHaveLength(1);
  });
});

describe("the conversation usage footer names its scope", () => {
  const USAGE_MESSAGES: UIMessage[] = [
    {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "data-lead-usage",
          data: { tokens: 1000, costUsd: "0.01", modelId: "openai:gpt" },
        },
        {
          type: "data-sub-agent-call",
          id: "c1",
          data: { tokens: 2000, costUsd: "0.02" },
        },
      ],
    },
  ];

  it("labels the visible line as this conversation's total", () => {
    renderComposer(true, { messages: USAGE_MESSAGES });
    expect(screen.getByTestId("conversation-usage")).toHaveTextContent(
      "Conversation · 3K tokens · $0.03",
    );
  });

  it("is keyboard reachable and explains the scope in its tooltip", async () => {
    renderComposer(true, { messages: USAGE_MESSAGES });
    const trigger = screen.getByTestId("conversation-usage");
    expect(trigger).toHaveAttribute("tabindex", "0");

    fireEvent.focus(trigger);
    await waitFor(() =>
      expect(
        screen.getAllByText("This conversation's total across all turns.").length,
      ).toBeGreaterThan(0),
    );
  });

  it("renders nothing when the conversation has no usage", () => {
    renderComposer(true);
    expect(screen.queryByTestId("conversation-usage")).toBe(null);
  });
});

describe("a slash command takes the Enter key alone", () => {
  function typeAndEnter(value: string): HTMLElement {
    const input = screen.getByTestId("message-input");
    fireEvent.change(input, { target: { value } });
    fireEvent.keyDown(input, { key: "Enter" });
    return input;
  }

  it("runs /help once and sends nothing", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    const input = typeAndEnter("/help");
    await waitFor(() => expect(input).toHaveValue("/"));
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "/newStart a new conversation",
      "/renameRename this conversation",
      "/exportExport the strategy, this conversation, or your latest gene set/save /download",
      "/importImport a gene set from pasted IDs",
      "/helpList the slash commands/?",
      "/clearClear the current strategy",
      "/analyzeAnalyze the current strategy and suggest next steps",
      "/summarizeSummarize this conversation",
      "/diagnoseDiagnose why my strategy returns 0 results",
      "/explainExplain a specific step",
    ]);
    expect(runCalls).toBe(0);
  });

  it("runs the highlighted command for a typed prefix and sends nothing", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    const input = typeAndEnter("/hel");
    await waitFor(() => expect(input).toHaveValue("/"));
    expect(runCalls).toBe(0);
  });

  it("prefills /summarize without sending it", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    const input = typeAndEnter("/summarize");
    await waitFor(() =>
      expect((input as HTMLTextAreaElement).value).toMatch(
        /^Summarize this conversation so far/,
      ),
    );
    expect(runCalls).toBe(0);
  });

  it("moves the highlight with the arrow keys", () => {
    renderComposer(true, { countingRuntime: true });
    const input = screen.getByTestId("message-input");
    fireEvent.change(input, { target: { value: "/" } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    const [, second] = screen.getAllByRole("option");
    expect(second).toHaveAttribute("aria-selected", "true");
  });

  it("refuses an unknown command, keeps its text and sends nothing", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    const input = typeAndEnter("/xyz");
    expect((await screen.findByRole("alert")).textContent).toBe(
      "No command /xyz. Type / to see the list.",
    );
    expect(input).toHaveValue("/xyz");
    expect(runCalls).toBe(0);
  });

  it("refuses an unknown command sent with the Send button", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    const input = screen.getByTestId("message-input");
    fireEvent.change(input, { target: { value: "/xyz" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "No command /xyz. Type / to see the list.",
    );
    expect(input).toHaveValue("/xyz");
    expect(runCalls).toBe(0);
  });

  it("drops the refusal once the text changes", async () => {
    renderComposer(true, { countingRuntime: true });
    const input = typeAndEnter("/xyz");
    await screen.findByRole("alert");
    fireEvent.change(input, { target: { value: "/xy" } });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(input).toHaveValue("/xy");
  });

  it("sends a message whose slash does not open it", async () => {
    runCalls = 0;
    renderComposer(true, { countingRuntime: true });
    typeAndEnter("compare with /xyz");
    await waitFor(() => expect(runCalls).toBe(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("closes the list on Escape", () => {
    renderComposer(true, { countingRuntime: true });
    const input = screen.getByTestId("message-input");
    fireEvent.change(input, { target: { value: "/ren" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveValue("");
  });
});
