/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

const toastError = vi.hoisted(() => vi.fn());
let conversationId = "";
const MESSAGE_ID = "bbbbbbb1-1111-4111-8111-111111111111";

vi.mock("next/navigation", () => ({
  usePathname: () => `/plasmodb/conversation/${conversationId}`,
}));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (state: { message: { id: string } }) => unknown) =>
    select({ message: { id: MESSAGE_ID } }),
}));

vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { server } from "../../../../vitest.msw-setup";
import { createTestWrapper } from "@/lib/query/testing";

import { RateMessageActions } from "./RateMessageActions";

const CONVERSATIONS = "http://localhost:3000/api/v1/conversations";

type Rating = "like" | "dislike";

interface Stubs {
  saved: Rating | null;
  calls: string[];
  putStatus: number;
  putDelayMs: Partial<Record<Rating, number>>;
}

function ratedBody(rating: Rating) {
  return { messageId: MESSAGE_ID, rating, ratedAt: "2026-09-24T09:00:00Z" };
}

function installHandlers(stubs: Stubs): void {
  const base = `${CONVERSATIONS}/${conversationId}`;
  const rating = `${base}/messages/${MESSAGE_ID}/rating`;
  server.use(
    http.get(`${base}/ratings`, () =>
      HttpResponse.json({
        ratings: stubs.saved === null ? [] : [ratedBody(stubs.saved)],
      }),
    ),
    http.put(rating, async ({ request }) => {
      const body = (await request.json()) as { rating: Rating };
      await delay(stubs.putDelayMs[body.rating] ?? 0);
      stubs.calls.push(`PUT ${body.rating}`);
      if (stubs.putStatus !== 200) {
        return HttpResponse.json(
          {
            type: "/errors/INTERNAL_ERROR",
            title: "Internal error",
            status: stubs.putStatus,
            code: "INTERNAL_ERROR",
          },
          { status: stubs.putStatus },
        );
      }
      stubs.saved = body.rating;
      return HttpResponse.json(ratedBody(body.rating));
    }),
    http.delete(rating, () => {
      stubs.calls.push("DELETE");
      stubs.saved = null;
      return new HttpResponse(null, { status: 204 });
    }),
  );
}

function stubs(overrides: Partial<Stubs> = {}): Stubs {
  return { saved: null, calls: [], putStatus: 200, putDelayMs: {}, ...overrides };
}

function renderActions(): void {
  const { Wrapper } = createTestWrapper();
  render(<RateMessageActions />, { wrapper: Wrapper });
}

const like = () => screen.getByRole("button", { name: "Good response" });
const dislike = () => screen.getByRole("button", { name: "Bad response" });

describe("RateMessageActions", () => {
  beforeEach(() => {
    conversationId = crypto.randomUUID();
    toastError.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the saved rating pressed when the thread opens", async () => {
    installHandlers(stubs({ saved: "dislike" }));
    renderActions();

    await waitFor(() => {
      expect(dislike()).toHaveAttribute("aria-pressed", "true");
    });
    expect(like()).toHaveAttribute("aria-pressed", "false");
  });

  it("presses like while the PUT is still pending", async () => {
    const state = stubs({ putDelayMs: { like: 400 } });
    installHandlers(state);
    renderActions();
    const user = userEvent.setup({ delay: null });

    await user.click(like());

    expect(like()).toHaveAttribute("aria-pressed", "true");
    expect(state.saved).toBeNull();
    await waitFor(() => {
      expect(state.saved).toBe("like");
    });
    expect(like()).toHaveAttribute("aria-pressed", "true");
  });

  it("returns to the saved rating and says why when the PUT fails", async () => {
    installHandlers(stubs({ saved: "like", putStatus: 500 }));
    renderActions();
    const user = userEvent.setup({ delay: null });
    await waitFor(() => {
      expect(like()).toHaveAttribute("aria-pressed", "true");
    });

    await user.click(dislike());

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledTimes(1);
    });
    expect(like()).toHaveAttribute("aria-pressed", "true");
    expect(dislike()).toHaveAttribute("aria-pressed", "false");
  });

  it("clears the rating with a DELETE when the pressed control is clicked", async () => {
    const state = stubs({ saved: "like" });
    installHandlers(state);
    renderActions();
    const user = userEvent.setup({ delay: null });
    await waitFor(() => {
      expect(like()).toHaveAttribute("aria-pressed", "true");
    });

    await user.click(like());

    await waitFor(() => {
      expect(state.calls).toEqual(["DELETE"]);
    });
    await waitFor(() => {
      expect(like()).toHaveAttribute("aria-pressed", "false");
    });
    expect(state.saved).toBeNull();
  });

  it("sends two quick clicks on one message in the order they were made", async () => {
    // The first request is the slower one, so the order holds only when the second waits.
    const state = stubs({ putDelayMs: { like: 300 } });
    installHandlers(state);
    renderActions();
    const user = userEvent.setup({ delay: null });

    await user.click(like());
    await user.click(dislike());

    await waitFor(() => {
      expect(state.calls).toEqual(["PUT like", "PUT dislike"]);
    });
    await waitFor(() => {
      expect(state.saved).toBe("dislike");
    });
    await waitFor(() => {
      expect(dislike()).toHaveAttribute("aria-pressed", "true");
    });
  });
});
