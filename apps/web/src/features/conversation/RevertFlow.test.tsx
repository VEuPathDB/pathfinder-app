/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

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

import { ChatShell } from "./ChatShell";

const CONVERSATION_ID = "11111111-1111-4111-8111-111111111111";
const FIRST_USER_ID = "aaaaaaa1-1111-4111-8111-111111111111";
const SECOND_USER_ID = "aaaaaaa2-1111-4111-8111-111111111111";
const FIRST_ASSISTANT_ID = "bbbbbbb1-1111-4111-8111-111111111111";
const SECOND_ASSISTANT_ID = "bbbbbbb2-1111-4111-8111-111111111111";

const BASE = `http://localhost:3000/api/v1/conversations/${CONVERSATION_ID}`;

function turn(
  userId: string,
  userText: string,
  assistantId: string,
  assistantText: string,
): unknown[] {
  return [
    {
      type: "user-message",
      message: { id: userId, role: "user", parts: [{ type: "text", text: userText }] },
    },
    { type: "start", messageId: assistantId },
    { type: "text-start", id: `${assistantId}-t` },
    { type: "text-delta", id: `${assistantId}-t`, delta: assistantText },
    { type: "text-end", id: `${assistantId}-t` },
    { type: "finish", finishReason: "stop" },
    { type: "done" },
  ];
}

const FIRST_TURN = turn(
  FIRST_USER_ID,
  "first question",
  FIRST_ASSISTANT_ID,
  "first answer",
);
const FULL_LOG = [
  ...FIRST_TURN,
  ...turn(SECOND_USER_ID, "second question", SECOND_ASSISTANT_ID, "second answer"),
];

const STRATEGY = {
  id: CONVERSATION_ID,
  name: "strategy",
  siteId: "plasmodb",
  steps: [],
  rootStepId: null,
  recordType: null,
  isSaved: false,
  createdAt: "2026-08-30T00:00:00Z",
  updatedAt: "2026-08-30T00:00:00Z",
};

interface ProblemBody {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
}

interface RevertStubs {
  calls: string[];
  revertStatus: number;
  revertBody: ProblemBody | null;
}

function installHandlers(stubs: RevertStubs): void {
  let snapshotCalls = 0;
  server.use(
    http.get(BASE, () => HttpResponse.json(STRATEGY)),
    http.get(`${BASE}/events/snapshot`, () => {
      snapshotCalls += 1;
      stubs.calls.push("snapshot");
      const chunks = snapshotCalls === 1 ? FULL_LOG : FIRST_TURN;
      return HttpResponse.json({ chunks, cursor: chunks.length });
    }),
    http.get(`${BASE}/events`, () => new HttpResponse(null, { status: 204 })),
    http.post(`${BASE}/revert-to-message`, () => {
      stubs.calls.push("revert");
      if (stubs.revertStatus === 204) return new HttpResponse(null, { status: 204 });
      return HttpResponse.json(stubs.revertBody, { status: stubs.revertStatus });
    }),
    http.post(`${BASE}/begin`, () => {
      stubs.calls.push("begin");
      return HttpResponse.json({
        conversationId: CONVERSATION_ID,
        isNew: false,
        name: "strategy",
      });
    }),
    http.post("http://localhost:3000/api/v1/feedback/actions", () =>
      HttpResponse.json({ accepted: true }),
    ),
    http.post("http://localhost:3000/api/v1/chat", () => {
      stubs.calls.push("chat");
      return new HttpResponse(null);
    }),
  );
}

/** The thread this tab created with its first message, reopened on its own id.
 * The shell is the subject: a revert reopens the thread through its key. */
function renderChat(): void {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn: true },
  );
  useSessionStore.setState({ createdConversationId: CONVERSATION_ID });
  render(<ChatShell />, { wrapper: Wrapper });
}

// Every wait here is on a snapshot or revert response served by msw, not on a
// timer. The budget covers that round trip on a loaded machine.
const ROUND_TRIP = { timeout: 20_000 };

/** Edit the second user message, then confirm Revert in the dialog. */
async function revertSecondTurn(): Promise<void> {
  const user = userEvent.setup({ delay: null });
  await waitFor(() => {
    expect(screen.getByText("second answer")).toBeInTheDocument();
  }, ROUND_TRIP);

  const editButtons = screen.getAllByRole("button", { name: "Edit" });
  await user.click(editButtons[editButtons.length - 1]!);

  const saveButton = await screen.findByTestId(
    "edit-composer-branch-or-revert",
    {},
    ROUND_TRIP,
  );
  const input = within(
    await screen.findByTestId("user-edit-composer", {}, ROUND_TRIP),
  ).getByRole("textbox");
  await user.clear(input);
  await user.paste("revised question");

  await user.click(saveButton);
  await user.click(screen.getByTestId("edit-revert-button"));
}

describe("revert truncates the client thread", { timeout: 30_000 }, () => {
  afterEach(() => {
    useSessionStore.getState().setPendingUserSubmission(null);
    useSessionStore.setState({ createdConversationId: null, chatResetCounter: 0 });
  });

  it("replaces the thread with the re-snapshotted log before the edit is sent", async () => {
    const stubs: RevertStubs = { calls: [], revertStatus: 204, revertBody: null };
    installHandlers(stubs);
    renderChat();

    await revertSecondTurn();

    await waitFor(() => {
      expect(screen.queryByText("second answer")).not.toBeInTheDocument();
    }, ROUND_TRIP);
    expect(screen.queryByText("second question")).not.toBeInTheDocument();
    expect(screen.getByText("first question")).toBeInTheDocument();
    expect(screen.getByText("first answer")).toBeInTheDocument();
    expect(screen.getByText("revised question")).toBeInTheDocument();

    await waitFor(() => {
      expect(stubs.calls).toContain("chat");
    }, ROUND_TRIP);
    expect(stubs.calls).toEqual(["snapshot", "revert", "snapshot", "begin", "chat"]);
  });

  it("keeps the dialog open with an error line when revert 404s", async () => {
    const stubs: RevertStubs = {
      calls: [],
      revertStatus: 404,
      revertBody: {
        type: "/errors/NOT_FOUND",
        title: "Target message not found",
        status: 404,
        code: "NOT_FOUND",
      },
    };
    installHandlers(stubs);
    renderChat();

    await revertSecondTurn();

    await waitFor(() => {
      expect(screen.getByTestId("edit-dialog-error")).toHaveTextContent(
        "Target message not found",
      );
    }, ROUND_TRIP);
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
    expect(screen.getByTestId("edit-branch-button")).toBeEnabled();
    expect(screen.getByText("second answer")).toBeInTheDocument();
    expect(stubs.calls).toEqual(["snapshot", "revert"]);
  });

  it("shows the login refusal when revert 401s without a VEuPathDB session", async () => {
    const stubs: RevertStubs = {
      calls: [],
      revertStatus: 401,
      revertBody: {
        type: "/errors/WDK_LOGIN_REQUIRED",
        title: "VEuPathDB login required",
        status: 401,
        detail:
          "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
        code: "WDK_LOGIN_REQUIRED",
      },
    };
    installHandlers(stubs);
    renderChat();

    await revertSecondTurn();

    await waitFor(() => {
      expect(screen.getByTestId("edit-dialog-error")).toHaveTextContent(
        "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
      );
    }, ROUND_TRIP);
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
    expect(screen.getByText("second answer")).toBeInTheDocument();
    expect(stubs.calls).toEqual(["snapshot", "revert"]);
  });

  it("keeps the dialog open with an error line when revert 409s", async () => {
    const stubs: RevertStubs = {
      calls: [],
      revertStatus: 409,
      revertBody: {
        type: "/errors/CONFLICT",
        title: "Unknown revision",
        status: 409,
        detail: "The thread moved on since this message was loaded.",
        code: "CONFLICT",
      },
    };
    installHandlers(stubs);
    renderChat();

    await revertSecondTurn();

    await waitFor(() => {
      expect(screen.getByTestId("edit-dialog-error")).toHaveTextContent(
        "The thread moved on since this message was loaded.",
      );
    }, ROUND_TRIP);
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
    expect(screen.getByText("second answer")).toBeInTheDocument();
    expect(stubs.calls).toEqual(["snapshot", "revert"]);
  });
});
