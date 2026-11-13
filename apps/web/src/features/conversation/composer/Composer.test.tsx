/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import type { ReactNode } from "react";
import type { UIMessage } from "ai";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => "/conversation",
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";
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

function makeChat(
  messages: UIMessage[],
  addToolApprovalResponse: ChatHelpers["addToolApprovalResponse"] = () => {},
): ChatHelpers {
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
    addToolApprovalResponse,
    clearError: () => {},
  };
}

function renderComposer(
  signedIn: boolean,
  options?: {
    hangingRuntime?: boolean;
    countingRuntime?: boolean;
    messages?: UIMessage[];
    respond?: ChatHelpers["addToolApprovalResponse"];
    assistantId?: string;
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
      <ChatHelpersProvider value={makeChat(options?.messages ?? [], options?.respond)}>
        <Composer
          conversationId="test-conversation"
          assistantId={options?.assistantId ?? "strategist"}
        />
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
  it("offers the mode switch in a strategy builder thread", () => {
    renderComposer(true);
    expect(screen.getByTestId("mode-switch")).toBeInTheDocument();
  });

  it("wraps its controls and gives Send a full tap target in a narrow window", () => {
    renderComposer(true);
    expect(screen.getByTestId("composer-controls")).toHaveClass("flex-wrap");
    expect(screen.getByTestId("send-button")).toHaveClass("max-[900px]:min-h-11");
    expect(screen.getByTestId("composer-footer")).toHaveClass("flex-wrap");
    expect(screen.getByTestId("ai-notice")).toHaveClass("min-w-64");
  });

  it("offers no mode switch in an audit thread", () => {
    renderComposer(true, { assistantId: "audit" });
    expect(screen.getByTestId("send-button")).toHaveTextContent("Send");
    expect(screen.queryByTestId("mode-switch")).toBeNull();
  });

  it("renders an input and send button for a signed-in user", () => {
    renderComposer(true);
    expect(screen.getByPlaceholderText(/ask about strategies/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("disables the composer while the session has no VEuPathDB login", () => {
    renderComposer(false);
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

describe("the composer's spend ring", () => {
  it("sits beside Attach once the conversation has usage", () => {
    renderComposer(false, {
      messages: [
        {
          id: "m1",
          role: "assistant",
          parts: [
            {
              type: "data-lead-usage",
              data: { tokens: 1000, costUsd: "0.01", modelId: "openai:gpt" },
            },
          ],
        },
      ],
    });
    expect(screen.getByTestId("spend-ring")).toHaveAccessibleName(
      "This conversation's spend",
    );
  });
});

describe("the composer says the assistant can make mistakes", () => {
  const NOTICE =
    "Strategist is an AI assistant and can make mistakes. Double-check important results.";

  it("shows the notice before the conversation has any usage", () => {
    renderComposer(true);
    expect(screen.getByTestId("ai-notice")).toHaveTextContent(NOTICE);
  });

  it("keeps the notice once the conversation has usage", () => {
    renderComposer(true, {
      messages: [
        {
          id: "m1",
          role: "assistant",
          parts: [
            {
              type: "data-lead-usage",
              data: { tokens: 1000, costUsd: "0.01", modelId: "openai:gpt" },
            },
          ],
        },
      ],
    });
    expect(screen.getByTestId("ai-notice")).toHaveTextContent(NOTICE);
    expect(screen.getByTestId("spend-ring")).toBeVisible();
  });
});

describe("the composer footer", () => {
  it("carries the notice and no Strategist mark", () => {
    renderComposer(true);

    expect(screen.getByTestId("ai-notice")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "VEuPathDB Strategist" })).toBeNull();
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

const COMBINE_PROMPT = "How should I combine the two gene sets?";
const ELSE_PROMPT = "Anything else I should know?";

const CONSULT_ASKS: UIMessage = {
  id: "m1",
  role: "assistant",
  parts: [
    {
      type: "tool-consult_user",
      toolCallId: "call_consult",
      state: "approval-requested",
      approval: { id: "approval-consult" },
      input: {
        questions: [
          {
            id: "combine_mode",
            kind: "single_choice",
            prompt: COMBINE_PROMPT,
            options: [{ label: "Union" }, { label: "Intersect" }],
            allowNotes: true,
          },
          {
            id: "anything_else",
            kind: "free_text",
            prompt: ELSE_PROMPT,
            options: [],
            allowNotes: true,
          },
        ],
      },
    },
  ],
};

const READINGS_ASKS: UIMessage = {
  id: "m1",
  role: "assistant",
  parts: [
    {
      type: "tool-consult_user",
      toolCallId: "call_readings",
      state: "approval-requested",
      approval: { id: "approval-readings" },
      input: {
        questions: [
          {
            id: "reading",
            kind: "single_choice",
            prompt: "Which reading should the strategy build?",
            options: [
              { label: "Genes with a predicted signal peptide" },
              { label: "Every protein-coding gene" },
            ],
            allowNotes: false,
          },
        ],
      },
    },
  ],
};

const DELETE_ASKS: UIMessage = {
  id: "m1",
  role: "assistant",
  parts: [
    {
      type: "tool-delete_step",
      toolCallId: "call_delete",
      state: "approval-requested",
      input: { step_id: "s2" },
      approval: { id: "approval-delete" },
    },
  ],
};

function typeAndSend(value: string): void {
  fireEvent.change(screen.getByTestId("message-input"), { target: { value } });
  fireEvent.click(screen.getByTestId("send-button"));
}

describe("a card waiting on the researcher docks on the composer", () => {
  beforeEach(() => {
    useConsultAnswersStore.setState({ byApprovalId: {} });
  });

  it("shows the open card above an input that asks for the researcher's own answer", () => {
    renderComposer(true, { messages: [DELETE_ASKS] });
    const dock = screen.getByTestId("docked-card");
    expect(screen.getByTestId("message-composer")).toContainElement(dock);
    expect(within(dock).getByTestId("approval-card-title")).toHaveTextContent(
      "Delete step needs your approval before it runs.",
    );
    const input = screen.getByTestId("message-input");
    expect(input).toBeEnabled();
    expect(input).toHaveAttribute("placeholder", "Or type your own answer");
  });

  it("docks nothing once the card is answered", () => {
    renderComposer(true, {
      messages: [
        DELETE_ASKS,
        { id: "u2", role: "user", parts: [{ type: "text", text: "Keep it." }] },
      ],
    });
    expect(screen.queryByTestId("docked-card")).toBeNull();
    expect(screen.getByTestId("message-input")).toHaveAttribute(
      "placeholder",
      "Ask about strategies, genes, or data... (try /help)",
    );
  });

  it("shows a consult one question at a time and names its place", () => {
    renderComposer(true, { messages: [CONSULT_ASKS] });
    const dock = screen.getByTestId("docked-card");
    expect(within(dock).getByTestId("consult-slide")).toHaveTextContent(COMBINE_PROMPT);
    expect(within(dock).getByTestId("consult-place")).toHaveTextContent("1 of 2");
    expect(within(dock).queryByText(ELSE_PROMPT)).toBeNull();
  });

  it("answers the current consult question with the typed words and sends no message", async () => {
    runCalls = 0;
    const respond = vi.fn();
    renderComposer(true, { messages: [CONSULT_ASKS], respond, countingRuntime: true });

    typeAndSend("Intersect, syntenic orthologs only");

    const dock = screen.getByTestId("docked-card");
    expect(await within(dock).findByTestId("consult-place")).toHaveTextContent(
      "2 of 2",
    );
    expect(screen.getByTestId("message-input")).toHaveValue("");
    expect(respond).not.toHaveBeenCalled();

    typeAndSend("nothing else");

    expect(respond.mock.calls).toEqual([[{ id: "approval-consult", approved: true }]]);
    expect(useConsultAnswersStore.getState().answersFor("approval-consult")).toEqual([
      {
        questionId: "combine_mode",
        prompt: COMBINE_PROMPT,
        chosenLabels: [],
        note: "Intersect, syntenic orthologs only",
      },
      {
        questionId: "anything_else",
        prompt: ELSE_PROMPT,
        chosenLabels: [],
        note: "nothing else",
      },
    ]);
    expect(runCalls).toBe(0);
  });

  it("answers the consult on Enter the same way", async () => {
    runCalls = 0;
    renderComposer(true, { messages: [CONSULT_ASKS], countingRuntime: true });
    const input = screen.getByTestId("message-input");
    fireEvent.change(input, { target: { value: "Union" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(
      await within(screen.getByTestId("docked-card")).findByTestId("consult-place"),
    ).toHaveTextContent("2 of 2");
    expect(runCalls).toBe(0);
  });

  it("leaves a slash command to the commands instead of answering the consult", () => {
    const respond = vi.fn();
    renderComposer(true, { messages: [CONSULT_ASKS], respond });

    typeAndSend("/clear");

    expect(
      within(screen.getByTestId("docked-card")).getByTestId("consult-place"),
    ).toHaveTextContent("1 of 2");
    expect(useConsultAnswersStore.getState().byApprovalId).toEqual({});
    expect(respond).not.toHaveBeenCalled();
  });

  it("sends typed words over a consult that takes no note as the next message", async () => {
    runCalls = 0;
    const respond = vi.fn();
    renderComposer(true, { messages: [READINGS_ASKS], respond, countingRuntime: true });

    typeAndSend("Only the genes expressed in the liver stage.");

    await waitFor(() => expect(runCalls).toBe(1));
    expect(respond).not.toHaveBeenCalled();
    expect(useConsultAnswersStore.getState().byApprovalId).toEqual({});
  });

  it("sends typed words under any other card as the researcher's next message", async () => {
    runCalls = 0;
    const respond = vi.fn();
    renderComposer(true, { messages: [DELETE_ASKS], respond, countingRuntime: true });

    typeAndSend("Keep that step and add the signal peptide search.");

    await waitFor(() => expect(runCalls).toBe(1));
    expect(respond).not.toHaveBeenCalled();
  });
});
