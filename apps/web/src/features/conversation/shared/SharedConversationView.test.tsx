/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { SharedConversation } from "@strategist/shared/generated/types/SharedConversation";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/shared/tok-1",
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(),
}));

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { chatUrl } from "@/lib/routes";

import { server } from "../../../../vitest.msw-setup";
import { SharedConversationView } from "./SharedConversationView";

const API = "http://localhost:3000/pathfinder/api/v1/shared/tok-1";
const PASSWORD = "Zq3-pw-from-owner";

const HEAD: SharedConversation = {
  name: "Kinases on chromosome 3",
  siteId: "plasmodb",
  assistantId: "strategist",
  allowCopy: false,
  cursor: 7,
  turnInFlight: false,
};

const CHUNKS = [
  {
    type: "user-message",
    message: {
      id: "u-1",
      role: "user",
      parts: [{ type: "text", text: "Which kinases sit on chromosome 3?" }],
    },
  },
  { type: "start", messageId: "a-1" },
  { type: "text-start", id: "t-1" },
  { type: "text-delta", id: "t-1", delta: "Twelve kinases sit on chromosome 3." },
  { type: "text-end", id: "t-1" },
  { type: "finish" },
  { type: "done" },
];

function serve({
  head = HEAD,
  password = null,
}: {
  head?: SharedConversation;
  password?: string | null;
} = {}): { copies: number } {
  const seen = { copies: 0 };
  const locked = (request: Request) =>
    password !== null && request.headers.get("X-Share-Password") !== password;
  const refusal = () =>
    HttpResponse.json(
      {
        title: "This link needs its password",
        status: 403,
        code: "SHARE_LOCKED",
      },
      { status: 403 },
    );
  server.use(
    http.get(API, ({ request }) =>
      locked(request) ? refusal() : HttpResponse.json(head),
    ),
    http.get(`${API}/snapshot`, ({ request }) =>
      locked(request) ? refusal() : HttpResponse.json({ chunks: CHUNKS, cursor: 7 }),
    ),
    http.post(`${API}/copy`, () => {
      seen.copies += 1;
      return HttpResponse.json({
        id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        name: "Kinases on chromosome 3 (copy)",
        siteId: "plasmodb",
        recordType: null,
        createdAt: "2026-11-09T12:00:00Z",
        updatedAt: "2026-11-09T12:00:00Z",
      });
    }),
  );
  return seen;
}

function show(signedIn = false) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions("plasmodb").queryKey, { signedIn });
  render(
    <SharedConversationView
      token="tok-1"
      signInUrl="https://qa.plasmodb.org/plasmo.qa/app/user/login"
    />,
    { wrapper: Wrapper },
  );
  return { queryClient };
}

afterEach(() => {
  pushMock.mockClear();
});

describe("SharedConversationView", () => {
  it("shows the thread under its name, marked read-only", async () => {
    serve();
    show();

    expect(
      await screen.findByText("Twelve kinases sit on chromosome 3."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: HEAD.name })).toBeInTheDocument();
    expect(screen.getByTestId("shared-read-only")).toHaveTextContent("Read-only");
    expect(screen.getByText("Which kinases sit on chromosome 3?")).toBeInTheDocument();
  });

  it("offers no control that acts on the thread", async () => {
    serve();
    show();
    await screen.findByText("Twelve kinases sit on chromosome 3.");

    for (const name of [
      /branch/i,
      /edit/i,
      /good response/i,
      /bad response/i,
      /regenerate/i,
      /send/i,
    ]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("says when the owner's conversation is answering", async () => {
    serve({ head: { ...HEAD, turnInFlight: true } });
    show();

    expect(await screen.findByTestId("shared-answering")).toHaveTextContent(
      "The conversation is answering. The reply shows here when it is done.",
    );
  });

  it("asks for the password and opens the thread with it", async () => {
    serve({ password: PASSWORD });
    show();

    const field = await screen.findByLabelText("Password");
    expect(screen.queryByText(HEAD.name)).toBeNull();
    await userEvent.type(field, PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));

    expect(
      await screen.findByText("Twelve kinases sit on chromosome 3."),
    ).toBeInTheDocument();
  });

  it("says when a password is wrong", async () => {
    serve({ password: PASSWORD });
    show();

    await userEvent.type(await screen.findByLabelText("Password"), "guess");
    await userEvent.click(screen.getByRole("button", { name: "Open" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That password does not open this conversation.",
    );
  });

  it("says when a link is no longer shared", async () => {
    server.use(
      http.get(API, () =>
        HttpResponse.json(
          {
            title: "This link is no longer shared",
            status: 404,
            code: "SHARE_NOT_FOUND",
          },
          { status: 404 },
        ),
      ),
    );
    show();

    expect(await screen.findByTestId("shared-gone")).toHaveTextContent(
      "This link is no longer shared.",
    );
  });

  it("offers no copy when the owner allows none", async () => {
    serve();
    show(true);
    await screen.findByText("Twelve kinases sit on chromosome 3.");

    expect(
      within(screen.getByTestId("shared-header")).queryAllByRole("button"),
    ).toHaveLength(0);
  });

  it("copies the thread for a signed-in viewer and opens the copy", async () => {
    const seen = serve({ head: { ...HEAD, allowCopy: true } });
    show(true);

    await userEvent.click(await screen.findByRole("button", { name: "Make a copy" }));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(
        chatUrl("7c9e6679-7425-40de-944b-e07fc1f90ae7"),
      ),
    );
    expect(seen.copies).toBe(1);
  });

  it("offers no copy while the conversation answers", async () => {
    serve({ head: { ...HEAD, allowCopy: true, turnInFlight: true } });
    show(true);

    await screen.findByTestId("shared-answering");
    expect(
      within(screen.getByTestId("shared-header")).queryAllByRole("button"),
    ).toHaveLength(0);
  });

  it("keeps the thread when one poll fails", async () => {
    serve();
    const { queryClient } = show();
    await screen.findByText("Twelve kinases sit on chromosome 3.");
    server.use(
      http.get(API, () => HttpResponse.json({ title: "Bad gateway" }, { status: 502 })),
    );

    await queryClient.refetchQueries({ queryKey: ["shared"] });

    expect(screen.getByText("Twelve kinases sit on chromosome 3.")).toBeVisible();
    expect(screen.queryByTestId("shared-gone")).toBeNull();
  });

  it("keeps the thread it shows when a newer turn cannot be read", async () => {
    serve();
    const { queryClient } = show();
    await screen.findByText("Twelve kinases sit on chromosome 3.");
    server.use(
      http.get(API, () => HttpResponse.json({ ...HEAD, cursor: 9 })),
      http.get(`${API}/snapshot`, () =>
        HttpResponse.json({ title: "Bad gateway" }, { status: 502 }),
      ),
    );

    await queryClient.refetchQueries({ queryKey: ["shared", "tok-1", null] });

    expect(
      await screen.findByTestId("shared-behind", {}, { timeout: 4000 }),
    ).toHaveTextContent("The newest turns could not be read yet. Trying again.");
    expect(screen.getByText("Twelve kinases sit on chromosome 3.")).toBeVisible();
  });

  it("says when the thread itself cannot be read", async () => {
    serve();
    server.use(
      http.get(`${API}/snapshot`, () =>
        HttpResponse.json({ title: "Bad gateway" }, { status: 502 }),
      ),
    );
    show();

    expect(
      await screen.findByTestId("shared-unreadable", {}, { timeout: 4000 }),
    ).toHaveTextContent("This conversation could not be read. Try again in a moment.");
  });

  it("asks a signed-out viewer to sign in before copying", async () => {
    serve({ head: { ...HEAD, allowCopy: true } });
    show(false);

    const header = await screen.findByTestId("shared-header");
    expect(
      within(header).getByRole("link", { name: "Sign in to make a copy" }),
    ).toHaveAttribute("href", "https://qa.plasmodb.org/plasmo.qa/app/user/login");
    expect(within(header).queryByRole("button", { name: "Make a copy" })).toBeNull();
  });
});
