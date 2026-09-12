/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import { useAuthGateStore } from "@/state/useAuthGateStore";

import { useChatRuntime } from "./useChatRuntime";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail:
    "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
  code: "WDK_LOGIN_REQUIRED",
};

const CONVERSATION_ID = "11111111-2222-4333-8444-555555555555";

/** `/begin` succeeds; the chat POST is refused for want of a VEuPathDB login. */
function stubChatRefusal(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) {
        return Promise.resolve(
          new Response(JSON.stringify(LOGIN_REQUIRED_BODY), {
            status: 401,
            statusText: "Unauthorized",
            headers: { "content-type": "application/problem+json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            conversationId: CONVERSATION_ID,
            isNew: true,
            name: "New conversation",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
}

beforeEach(() => {
  useAuthGateStore.getState().dismissSignIn();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useChatRuntime onError", () => {
  it("routes a chat-transport 401 problem+json to the VEuPathDB sign-in prompt", async () => {
    stubChatRefusal();
    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: CONVERSATION_ID }),
    );

    await act(async () => {
      await result.current.chat.sendMessage({ text: "show me kinase genes" });
    });

    await waitFor(() => {
      expect(useAuthGateStore.getState().signInRequired).toBe(true);
    });
    expect(useAuthGateStore.getState().signInReason).toBe(LOGIN_REQUIRED_BODY.detail);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      LOGIN_REQUIRED_BODY.detail,
      expect.objectContaining({ id: expect.any(String) }),
    );
  });
});
