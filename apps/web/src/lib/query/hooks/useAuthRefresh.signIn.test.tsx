// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { getMyQuotaQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyQuota";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";

import { useAuthRefresh } from "./useAuthRefresh";

const QUOTA = {
  usedUsd: "0",
  limitUsd: "10.00",
  totalTokens: 0,
  percent: 0,
  resetsAt: "2026-11-01T00:00:00Z",
  ownKeyUsd: "0",
  ownKeyTokens: 0,
  ownKeyProviders: [],
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

/** Answers the status with the current sign-in state and logs every request in order. */
function website() {
  const state = { signedIn: true };
  const log: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const path = new URL(input, "http://localhost").pathname;
      if (path.endsWith("/auth/status")) {
        log.push(`status:${state.signedIn ? "in" : "out"}`);
        return Promise.resolve(json({ signedIn: state.signedIn }));
      }
      if (path.endsWith("/auth/refresh") && init?.method === "POST") {
        log.push("refresh");
        return Promise.resolve(json({ success: true }));
      }
      if (path.endsWith("/me/quota")) {
        log.push("quota");
        return Promise.resolve(json(QUOTA));
      }
      return new Promise<Response>(() => {});
    }),
  );
  return { state, log };
}

function UserScopedRead() {
  useQuery(getMyQuotaQueryOptions());
  return null;
}

function Shell() {
  const { data } = useQuery(authStatusOptions("plasmodb"));
  const { authRefreshed } = useAuthRefresh("plasmodb");
  const ready = data?.signedIn === true && authRefreshed;
  return ready ? <UserScopedRead /> : null;
}

describe("useAuthRefresh across a website sign-out", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("posts a second refresh before any user-scoped read after signing in again", async () => {
    const { state, log } = website();
    const { queryClient, Wrapper } = createTestWrapper();
    const status = authStatusOptions("plasmodb").queryKey;
    await act(async () => {
      render(
        <Wrapper>
          <Shell />
        </Wrapper>,
      );
    });
    await vi.waitFor(() => expect(log).toContain("quota"));

    state.signedIn = false;
    await act(() => queryClient.refetchQueries({ queryKey: status }));
    state.signedIn = true;
    await act(() => queryClient.refetchQueries({ queryKey: status }));

    await vi.waitFor(() =>
      expect(log).toEqual([
        "status:in",
        "refresh",
        "quota",
        "status:out",
        "status:in",
        "refresh",
        "quota",
      ]),
    );
  });
});
