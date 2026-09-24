/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => `/plasmodb/conversation/${conversationId}`,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../rail/RightRail", () => ({ RightRail: () => null }));

import { server } from "../../../../vitest.msw-setup";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatShell } from "../ChatShell";
import { messageAnchorId } from "../thread/messageAnchor";

let conversationId = "";
const USER_ID = "aaaaaaa1-1111-4111-8111-111111111111";
const ASSISTANT_ID = "bbbbbbb1-1111-4111-8111-111111111111";
const CONVERSATIONS = "http://localhost:3000/api/v1/conversations";
const ROUND_TRIP = { timeout: 20_000 };

const LOG = [
  {
    type: "user-message",
    message: {
      id: USER_ID,
      role: "user",
      parts: [{ type: "text", text: "find kinases" }],
    },
  },
  { type: "start", messageId: ASSISTANT_ID },
  { type: "text-start", id: `${ASSISTANT_ID}-t` },
  { type: "text-delta", id: `${ASSISTANT_ID}-t`, delta: "142 kinases." },
  { type: "text-end", id: `${ASSISTANT_ID}-t` },
  { type: "finish", finishReason: "stop" },
  { type: "done" },
];

function installHandlers(): void {
  const base = `${CONVERSATIONS}/${conversationId}`;
  server.use(
    http.get(base, () =>
      HttpResponse.json({
        id: conversationId,
        name: "kinases",
        siteId: "plasmodb",
        steps: [],
        rootStepId: null,
        recordType: null,
        isSaved: false,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      }),
    ),
    http.get(`${base}/events/snapshot`, () =>
      HttpResponse.json({ chunks: LOG, cursor: LOG.length }),
    ),
    http.get(
      `${CONVERSATIONS}/:id/events`,
      () => new HttpResponse(null, { status: 204 }),
    ),
    http.get(`${base}/ratings`, () =>
      HttpResponse.json({
        ratings: [
          {
            messageId: ASSISTANT_ID,
            rating: "dislike",
            ratedAt: "2026-09-24T09:00:00Z",
          },
        ],
      }),
    ),
  );
}

function renderChat(): void {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn: true },
  );
  useSessionStore.setState({ createdConversationId: conversationId });
  render(<ChatShell />, { wrapper: Wrapper });
}

describe("the rating controls in the thread", { timeout: 30_000 }, () => {
  beforeEach(() => {
    conversationId = crypto.randomUUID();
  });

  afterEach(() => {
    sessionStorage.clear();
    useSessionStore.setState({ createdConversationId: null, chatResetCounter: 0 });
  });

  it("sit on the assistant message only, with its saved rating pressed", async () => {
    installHandlers();
    renderChat();

    await waitFor(() => {
      expect(screen.getByText("142 kinases.")).toBeInTheDocument();
    }, ROUND_TRIP);

    const reply = document.getElementById(messageAnchorId(ASSISTANT_ID));
    expect(reply).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Good response" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Bad response" })).toHaveLength(1);
    const inReply = within(reply!);
    await waitFor(() => {
      expect(inReply.getByRole("button", { name: "Bad response" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }, ROUND_TRIP);
    expect(inReply.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});
