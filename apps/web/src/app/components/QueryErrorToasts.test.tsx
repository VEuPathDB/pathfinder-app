/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { toast } from "sonner";

import { APIError } from "@/lib/api/http";
import { __makeQueryClientForTests, setQueryErrorHandler } from "@/lib/query/client";
import {
  WDK_LOGIN_REQUIRED_TOAST_ID,
  useAuthGateStore,
} from "@/state/useAuthGateStore";

import { QueryErrorToasts } from "./QueryErrorToasts";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail: "Sign in to VEuPathDB to use searches, strategies and gene sets.",
  code: "WDK_LOGIN_REQUIRED",
};

/** Drive a failing query through the handler the component registered. */
async function failQuery(error: unknown): Promise<void> {
  await __makeQueryClientForTests()
    .fetchQuery({
      queryKey: ["gene-sets", crypto.randomUUID()],
      queryFn: () => Promise.reject(error),
      retry: false,
    })
    .catch(() => {});
}

beforeEach(() => {
  useAuthGateStore.getState().dismissSignIn();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  setQueryErrorHandler(null);
});

describe("QueryErrorToasts", () => {
  it("reports an unrelated query failure as a toast", async () => {
    render(<QueryErrorToasts />);

    await failQuery(new Error("network down"));

    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("network down");
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
  });

  it("turns a refusal about the VEuPathDB account into the sign-in request", async () => {
    render(<QueryErrorToasts />);

    await failQuery(
      new APIError(LOGIN_REQUIRED_BODY.detail, {
        status: 401,
        statusText: "Unauthorized",
        url: "/api/v1/gene-sets",
        data: LOGIN_REQUIRED_BODY,
      }),
    );

    expect(useAuthGateStore.getState().signInRequired).toBe(true);
    expect(useAuthGateStore.getState().signInReason).toBe(LOGIN_REQUIRED_BODY.detail);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(LOGIN_REQUIRED_BODY.detail, {
      id: WDK_LOGIN_REQUIRED_TOAST_ID,
    });
  });

  it("drops nothing on the floor when no query fails", () => {
    const { baseElement } = render(<QueryErrorToasts />);

    expect(baseElement.querySelectorAll("*")).toHaveLength(1);
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
  });
});
