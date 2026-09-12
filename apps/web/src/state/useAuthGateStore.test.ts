/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { z } from "zod";

import { APIError, requestJson } from "@/lib/api/http";
import { refreshAuth } from "@/lib/api/veupathdb-auth";
import {
  WDK_LOGIN_REQUIRED_TOAST_ID,
  handleWdkAuthRefusal,
  requiresFullScreenSignIn,
  useAuthGateStore,
} from "./useAuthGateStore";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("@/lib/api/veupathdb-auth", () => ({ refreshAuth: vi.fn() }));

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail:
    "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
  code: "WDK_LOGIN_REQUIRED",
};

const IDENTITY_MISMATCH_BODY = {
  type: "about:blank",
  title: "VEuPathDB account changed",
  status: 401,
  detail:
    "Signed in to VEuPathDB as a different account than this PathFinder session. Sign in again.",
  code: "WDK_IDENTITY_MISMATCH",
};

function mismatchError(): APIError {
  return new APIError(IDENTITY_MISMATCH_BODY.detail, {
    status: 401,
    statusText: "Unauthorized",
    url: "/api/v1/eda/viz",
    data: IDENTITY_MISMATCH_BODY,
  });
}

beforeEach(() => {
  useAuthGateStore.getState().dismissSignIn();
  vi.mocked(toast.error).mockClear();
  vi.mocked(refreshAuth).mockReset();
  vi.mocked(refreshAuth).mockResolvedValue({ success: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useAuthGateStore", () => {
  it("starts closed", () => {
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
    expect(useAuthGateStore.getState().signInReason).toBeNull();
  });

  it("opens without a reason when the user asks to sign in", () => {
    useAuthGateStore.getState().requestSignIn();
    expect(useAuthGateStore.getState().signInRequired).toBe(true);
    expect(useAuthGateStore.getState().signInReason).toBeNull();
  });

  it("keeps the reason the server gave and clears it on dismiss", () => {
    useAuthGateStore.getState().requestSignIn(LOGIN_REQUIRED_BODY.detail);
    expect(useAuthGateStore.getState().signInReason).toBe(LOGIN_REQUIRED_BODY.detail);
    useAuthGateStore.getState().dismissSignIn();
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
    expect(useAuthGateStore.getState().signInReason).toBeNull();
  });

  it("does not replace the state when the same request repeats", () => {
    useAuthGateStore.getState().requestSignIn(LOGIN_REQUIRED_BODY.detail);
    const first = useAuthGateStore.getState();
    useAuthGateStore.getState().requestSignIn(LOGIN_REQUIRED_BODY.detail);
    expect(useAuthGateStore.getState()).toBe(first);
  });
});

describe("handleWdkAuthRefusal", () => {
  it("opens the sign-in prompt and reports the server detail once", () => {
    const err = new APIError(LOGIN_REQUIRED_BODY.detail, {
      status: 401,
      statusText: "Unauthorized",
      url: "/api/v1/conversations/c1/begin",
      data: LOGIN_REQUIRED_BODY,
    });
    expect(handleWdkAuthRefusal(err)).toBe(true);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
      { id: WDK_LOGIN_REQUIRED_TOAST_ID },
    );
    expect(useAuthGateStore.getState().signInRequired).toBe(true);
    expect(useAuthGateStore.getState().signInReason).toBe(LOGIN_REQUIRED_BODY.detail);
    expect(vi.mocked(refreshAuth)).not.toHaveBeenCalled();
  });

  it("reuses one toast id so concurrent refusals do not stack", () => {
    const err = new APIError(LOGIN_REQUIRED_BODY.detail, {
      status: 401,
      statusText: "Unauthorized",
      url: "/api/v1/gene-sets",
      data: LOGIN_REQUIRED_BODY,
    });
    handleWdkAuthRefusal(err);
    handleWdkAuthRefusal(err);
    expect(vi.mocked(toast.error).mock.calls.map((call) => call[1])).toEqual([
      { id: WDK_LOGIN_REQUIRED_TOAST_ID },
      { id: WDK_LOGIN_REQUIRED_TOAST_ID },
    ]);
  });

  it("leaves other errors to their own handler", () => {
    const err = new APIError("Conversation not found", {
      status: 404,
      statusText: "Not Found",
      url: "/x",
      data: { title: "Not found", status: 404, detail: "gone", code: "NOT_FOUND" },
    });
    expect(handleWdkAuthRefusal(err)).toBe(false);
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
  });

  it("routes a real 401 problem+json response from the API layer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Response(JSON.stringify(LOGIN_REQUIRED_BODY), {
            status: 401,
            statusText: "Unauthorized",
            headers: { "content-type": "application/problem+json" },
          }),
      ),
    );

    const thrown = await requestJson(z.object({}), "/api/v1/conversations/c1/begin", {
      method: "POST",
      body: { siteId: "plasmodb" },
    }).catch((err: unknown) => err);

    expect(handleWdkAuthRefusal(thrown)).toBe(true);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
      { id: WDK_LOGIN_REQUIRED_TOAST_ID },
    );
    expect(useAuthGateStore.getState().signInRequired).toBe(true);
  });
});

describe("handleWdkAuthRefusal on a second VEuPathDB account", () => {
  it("relinks the session and retries instead of prompting", async () => {
    const retry = vi.fn();

    expect(handleWdkAuthRefusal(mismatchError(), retry)).toBe(true);

    await vi.waitFor(() => expect(retry).toHaveBeenCalledTimes(1));
    expect(vi.mocked(refreshAuth)).toHaveBeenCalledTimes(1);
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
  });

  it("relinks once for a burst of refusals", async () => {
    const retry = vi.fn();

    handleWdkAuthRefusal(mismatchError(), retry);
    handleWdkAuthRefusal(mismatchError(), retry);

    await vi.waitFor(() => expect(retry).toHaveBeenCalledTimes(2));
    expect(vi.mocked(refreshAuth)).toHaveBeenCalledTimes(1);
  });

  it("prompts with the server detail when the relink fails", async () => {
    vi.mocked(refreshAuth).mockRejectedValue(
      new APIError("No VEuPathDB session", {
        status: 401,
        statusText: "Unauthorized",
        url: "/api/v1/veupathdb/auth/refresh",
        data: null,
      }),
    );
    const retry = vi.fn();

    handleWdkAuthRefusal(mismatchError(), retry);

    await vi.waitFor(() =>
      expect(useAuthGateStore.getState().signInRequired).toBe(true),
    );
    expect(useAuthGateStore.getState().signInReason).toBe(
      IDENTITY_MISMATCH_BODY.detail,
    );
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(IDENTITY_MISMATCH_BODY.detail, {
      id: WDK_LOGIN_REQUIRED_TOAST_ID,
    });
    expect(retry).not.toHaveBeenCalled();
  });

  it("prompts when the relink answers that it did not succeed", async () => {
    vi.mocked(refreshAuth).mockResolvedValue({ success: false });

    handleWdkAuthRefusal(mismatchError());

    await vi.waitFor(() =>
      expect(useAuthGateStore.getState().signInRequired).toBe(true),
    );
  });
});

describe("requiresFullScreenSignIn", () => {
  it("blocks a standalone session that has no VEuPathDB login", () => {
    expect(requiresFullScreenSignIn({ embedded: false, signedIn: false })).toBe(true);
  });

  it("lets an embedded session render so the composer can carry the prompt", () => {
    expect(requiresFullScreenSignIn({ embedded: true, signedIn: false })).toBe(false);
  });

  it("never blocks a signed-in session", () => {
    expect(requiresFullScreenSignIn({ embedded: false, signedIn: true })).toBe(false);
    expect(requiresFullScreenSignIn({ embedded: true, signedIn: true })).toBe(false);
  });
});
