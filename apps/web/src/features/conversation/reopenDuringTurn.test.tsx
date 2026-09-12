/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => `/plasmodb/conversation/${CONVERSATION_ID}`,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("./rail/RightRail", () => ({ RightRail: () => null }));

import { server } from "../../../vitest.msw-setup";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatView } from "./ChatView";

const BASE = `http://localhost:3000/api/v1/conversations/${CONVERSATION_ID}`;
const CURSOR = 220744;

const STRATEGY = {
  id: CONVERSATION_ID,
  name: "kinase strategy",
  siteId: "plasmodb",
  steps: [],
  rootStepId: null,
  recordType: null,
  isSaved: false,
  createdAt: "2026-09-12T00:00:00Z",
  updatedAt: "2026-09-12T00:00:00Z",
};

const PROMPT = {
  type: "user-message",
  message: {
    id: "11111111-1111-4111-8111-111111111111",
    role: "user",
    parts: [{ type: "text", text: "build a kinase strategy" }],
  },
};

const TURN = [
  { type: "start", messageId: "22222222-2222-4222-8222-222222222222" },
  { type: "start-step" },
  {
    type: "tool-input-available",
    toolCallId: "call_1",
    toolName: "set_criterion",
    input: { criterionId: "c1" },
  },
  { type: "tool-output-available", toolCallId: "call_1", output: { ok: true } },
  { type: "finish-step" },
  { type: "finish", finishReason: "stop" },
];

function tailBody(): string {
  const frames = TURN.map(
    (chunk, index) =>
      `id: ${String(CURSOR + index + 1)}\ndata: ${JSON.stringify(chunk)}\n\n`,
  );
  return `${frames.join("")}id: ${String(CURSOR + TURN.length + 1)}\ndata: [DONE]\n\n`;
}

function serveThread(snapshotChunks: unknown[], turnAlive = true): string[] {
  const tails: string[] = [];
  server.use(
    http.get(BASE, () => HttpResponse.json(STRATEGY)),
    http.get(`${BASE}/events/snapshot`, () =>
      HttpResponse.json({ chunks: snapshotChunks, cursor: CURSOR }),
    ),
    http.get(`${BASE}/events`, ({ request }) => {
      tails.push(new URL(request.url).search);
      if (!turnAlive) return new HttpResponse(null, { status: 204 });
      return new HttpResponse(tailBody(), {
        headers: { "content-type": "text/event-stream" },
      });
    }),
  );
  return tails;
}

function renderThread(): void {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn: true },
  );
  render(<ChatView conversationId={CONVERSATION_ID} resumable />, { wrapper: Wrapper });
}

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("a thread reopened while its turn runs", () => {
  it("tails from the snapshot's cursor and draws what the turn has logged", async () => {
    const tails = serveThread([PROMPT]);

    renderThread();

    await waitFor(() => {
      expect(tails).toEqual([`?after=${String(CURSOR)}`]);
    });
    expect(await screen.findByText("build a kinase strategy")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByTestId("trace-row")).toHaveLength(1);
    });
  });

  it("keeps the snapshot when the tail reports the turn wrote nothing", async () => {
    const tails = serveThread([PROMPT], false);

    renderThread();

    await waitFor(() => {
      expect(tails).toEqual([`?after=${String(CURSOR)}`]);
    });
    expect(await screen.findByText("build a kinase strategy")).toBeInTheDocument();
    expect(screen.queryByTestId("trace-row")).toBeNull();
  });

  it("opens no tail on a thread whose last turn ended", async () => {
    const tails = serveThread([
      PROMPT,
      { type: "start", messageId: "22222222-2222-4222-8222-222222222222" },
      { type: "finish", finishReason: "stop" },
      { type: "done" },
    ]);

    renderThread();

    expect(await screen.findByText("build a kinase strategy")).toBeInTheDocument();
    expect(tails).toEqual([]);
  });
});
