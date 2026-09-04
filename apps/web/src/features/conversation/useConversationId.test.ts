// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const { route } = vi.hoisted(() => ({
  route: { pathname: null as string | null },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
}));

import { useConversationId } from "./useConversationId";

beforeEach(() => {
  route.pathname = null;
});

describe("useConversationId", () => {
  it("reads the id from a site-prefixed conversation path", () => {
    route.pathname = "/plasmodb/conversation/conv-1";
    expect(renderHook(() => useConversationId()).result.current).toBe("conv-1");
  });

  it("reads the id from a path with a trailing segment", () => {
    route.pathname = "/plasmodb/conversation/conv-2/eda";
    expect(renderHook(() => useConversationId()).result.current).toBe("conv-2");
  });

  it("is null when the router reports no pathname", () => {
    expect(renderHook(() => useConversationId()).result.current).toBe(null);
  });

  it("is null on a path that names no conversation", () => {
    route.pathname = "/plasmodb/workbench";
    expect(renderHook(() => useConversationId()).result.current).toBe(null);
  });
});
