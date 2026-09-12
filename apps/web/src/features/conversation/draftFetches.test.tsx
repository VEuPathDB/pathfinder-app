/**
 * @vitest-environment jsdom
 */
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { QueryClient } from "@tanstack/react-query";

const DRAFT_PATH = "/plasmodb/conversation";

let pathname = DRAFT_PATH;

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("./rail/RightRail", () => ({ RightRail: () => null }));

import { redirect } from "next/navigation";

import { server } from "../../../vitest.msw-setup";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { conversationSnapshotOptions } from "@/features/conversation/api/conversationSnapshot";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatShell } from "./ChatShell";
import { ChatView } from "./ChatView";

const CONVERSATION_ID = "22222222-2222-4222-8222-222222222222";
const BASE = `http://localhost:3000/api/v1/conversations/${CONVERSATION_ID}`;

const STRATEGY = {
  id: CONVERSATION_ID,
  name: "strategy",
  siteId: "plasmodb",
  steps: [],
  rootStepId: null,
  recordType: null,
  isSaved: false,
  createdAt: "2026-09-12T00:00:00Z",
  updatedAt: "2026-09-12T00:00:00Z",
};

function recordReads(detailStatus = 200): string[] {
  const seen: string[] = [];
  server.use(
    http.get(BASE, () => {
      seen.push("detail");
      if (detailStatus !== 200) return new HttpResponse(null, { status: detailStatus });
      return HttpResponse.json(STRATEGY);
    }),
    http.get(`${BASE}/events/snapshot`, () => {
      seen.push("snapshot");
      return HttpResponse.json({ chunks: [], cursor: 0 });
    }),
    http.get(`${BASE}/events`, () => new HttpResponse(null, { status: 204 })),
  );
  return seen;
}

function signedIn(queryClient: QueryClient): void {
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn: true },
  );
}

function renderView(): void {
  const { queryClient, Wrapper } = createTestWrapper();
  signedIn(queryClient);
  render(
    <ChatView conversationId={CONVERSATION_ID} resumable={pathname !== DRAFT_PATH} />,
    {
      wrapper: Wrapper,
    },
  );
}

afterEach(() => {
  useSessionStore.setState({ createdConversationId: null, chatResetCounter: 0 });
  vi.restoreAllMocks();
  pathname = DRAFT_PATH;
});

describe("a draft thread", () => {
  it("reads neither the conversation nor its snapshot", async () => {
    const seen = recordReads();

    renderView();

    expect(await screen.findByTestId("message-composer")).toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  it("reads the conversation once its first message has created the row", async () => {
    const seen = recordReads();

    renderView();
    expect(await screen.findByTestId("message-composer")).toBeInTheDocument();

    act(() => {
      useSessionStore.getState().markConversationCreated(CONVERSATION_ID);
    });

    await waitFor(() => {
      expect(seen).toContain("detail");
    });
  });

  it("is not redirected away when the conversation read answers 404", async () => {
    recordReads(404);

    renderView();
    expect(await screen.findByTestId("message-composer")).toBeInTheDocument();

    act(() => {
      useSessionStore.getState().markConversationCreated(CONVERSATION_ID);
    });

    await waitFor(() => {
      expect(screen.getByTestId("message-composer")).toBeInTheDocument();
    });
    expect(vi.mocked(redirect)).not.toHaveBeenCalled();
  });
});

describe("a thread the route names", () => {
  it("reads the conversation and its snapshot", async () => {
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;
    const seen = recordReads();

    renderView();

    expect(await screen.findByTestId("message-composer")).toBeInTheDocument();
    expect(seen).toContain("detail");
    expect(seen).toContain("snapshot");
  });
});

describe("a thread this tab created, reopened on its own id", () => {
  it("reads its transcript instead of rendering an empty thread", async () => {
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;
    // The shell mints the id, so the id the route carries is the one this tab
    // generated.
    vi.spyOn(crypto, "randomUUID").mockReturnValue(CONVERSATION_ID);
    useSessionStore.setState({ createdConversationId: CONVERSATION_ID });
    const seen = recordReads();

    const { queryClient, Wrapper } = createTestWrapper();
    signedIn(queryClient);
    render(<ChatShell />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(seen).toContain("snapshot");
    });
    expect(seen).toContain("detail");
  });
});

describe("a revert on the mount that created the thread", () => {
  it("reads the transcript once, after the revert and not during the turn", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(CONVERSATION_ID);
    const seen = recordReads();

    const { queryClient, Wrapper } = createTestWrapper();
    signedIn(queryClient);
    render(<ChatShell />, { wrapper: Wrapper });
    expect(await screen.findByTestId("message-composer")).toBeInTheDocument();

    // The first turn creates the row and rewrites the URL to name it. Reading
    // the transcript of a turn in flight clears the record the transport
    // replays that turn from, so no read may happen here.
    act(() => {
      useSessionStore.getState().markConversationCreated(CONVERSATION_ID);
    });
    await waitFor(() => {
      expect(seen).toContain("detail");
    });
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;

    // What the revert does: drop the transcript, then remount the thread.
    await act(async () => {
      await queryClient.invalidateQueries({
        queryKey: conversationSnapshotOptions(CONVERSATION_ID).queryKey,
      });
      useSessionStore.getState().bumpChatResetCounter();
    });

    await waitFor(() => {
      expect(seen).toContain("snapshot");
    });
    expect(seen).toEqual(["detail", "snapshot"]);
  });
});
