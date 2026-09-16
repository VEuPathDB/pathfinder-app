/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";

import { QuotaPill } from "./QuotaPill";

const SITE = "plasmodb";

const QUOTA = {
  usedUsd: "1.25",
  limitUsd: "10.00",
  totalTokens: 123456,
  percent: 12.5,
  resetsAt: "2026-10-01T00:00:00Z",
};

const quotaReads: string[] = [];
const server = setupServer(
  http.get("http://localhost:3000/api/v1/me/quota", ({ request }) => {
    quotaReads.push(request.url);
    return HttpResponse.json(QUOTA);
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPill(signedIn = true) {
  quotaReads.length = 0;
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions(SITE).queryKey, {
    signedIn,
    name: "Researcher",
    email: "researcher@upenn.edu",
  });
  return render(<QuotaPill siteId={SITE} />, { wrapper: Wrapper });
}

describe("QuotaPill", () => {
  it("shows the account's spend against its monthly limit", async () => {
    renderPill();
    const pill = await screen.findByLabelText("Monthly quota");
    expect(pill).toHaveTextContent("$1.25 / $10.00");
  });

  it("is keyboard reachable and names the account-month scope in its tooltip", async () => {
    renderPill();
    const pill = await screen.findByLabelText("Monthly quota");
    expect(pill).toHaveAttribute("tabindex", "0");

    fireEvent.focus(pill);
    await waitFor(() =>
      expect(
        screen.getAllByText("Account total this month, across all conversations.")
          .length,
      ).toBeGreaterThan(0),
    );
    expect(screen.getAllByText(/123\.5K tokens · resets/).length).toBeGreaterThan(0);
  });

  it("asks for no quota while the reader is signed out", async () => {
    renderPill(false);

    await waitFor(() => expect(screen.queryByLabelText("Monthly quota")).toBeNull());
    expect(quotaReads).toEqual([]);
  });
});
