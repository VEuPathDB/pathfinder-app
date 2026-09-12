/**
 * @vitest-environment jsdom
 */
import type * as ReactQueryModule from "@tanstack/react-query";
import { describe, it, expect, beforeEach, vi } from "vitest";

import {
  computeChatResolution,
  draftRoute,
  isEdaRoute,
  isStrategyRoute,
} from "./ChatShell";

type ReactQueryExports = typeof ReactQueryModule;

describe("ChatShell.computeChatResolution", () => {
  it("uses the generated id on the bare conversation route", () => {
    const r = computeChatResolution({
      pathname: "/conversation",
      generatedChatId: "gen-1",
    });
    expect(r.conversationId).toBe("gen-1");
  });

  it("keeps the generated id after the URL rewrites to it", () => {
    const r = computeChatResolution({
      pathname: "/conversation/gen-1",
      generatedChatId: "gen-1",
    });
    expect(r.conversationId).toBe("gen-1");
  });

  it("uses the URL id when the route names a conversation", () => {
    const r = computeChatResolution({
      pathname: "/conversation/existing-id",
      generatedChatId: "gen-1",
    });
    expect(r.conversationId).toBe("existing-id");
  });
});

describe("ChatShell.computeChatResolution resumability", () => {
  it("has nothing to resume before the URL carries an id", () => {
    const r = computeChatResolution({
      pathname: "/conversation",
      generatedChatId: "gen-1",
    });
    expect(r.resumable).toBe(false);
  });

  it("resumes an existing conversation", () => {
    const r = computeChatResolution({
      pathname: "/conversation/existing-id",
      generatedChatId: "gen-1",
    });
    expect(r.resumable).toBe(true);
  });

  it("resumes a conversation this tab named, once the URL carries its id", () => {
    // The id is generated locally, so it stays equal to the generated id for
    // the life of the tab. A running turn must still be re-attachable.
    const r = computeChatResolution({
      pathname: "/conversation/gen-1",
      generatedChatId: "gen-1",
    });
    expect(r.resumable).toBe(true);
  });
});

describe("ChatShell.isStrategyRoute", () => {
  it("returns false for the bare conversation route", () => {
    expect(isStrategyRoute("/plasmodb/conversation/conv-1")).toBe(false);
    expect(isStrategyRoute("/plasmodb/conversation")).toBe(false);
  });

  it("returns true for the strategy page route", () => {
    expect(isStrategyRoute("/plasmodb/conversation/conv-1/strategy")).toBe(true);
  });

  it("returns true for the strategy step deep-link route", () => {
    expect(isStrategyRoute("/plasmodb/conversation/conv-1/strategy/step/step_1")).toBe(
      true,
    );
  });
});

describe("ChatShell.isEdaRoute", () => {
  it("matches the conversation-scoped eda pane", () => {
    expect(isEdaRoute("/plasmodb/conversation/conv-1/eda")).toBe(true);
  });

  it("matches a nested eda path", () => {
    expect(isEdaRoute("/plasmodb/conversation/conv-1/eda/anything")).toBe(true);
  });

  it("does not match the chat thread itself", () => {
    expect(isEdaRoute("/plasmodb/conversation/conv-1")).toBe(false);
  });

  it("does not match a conversation whose id ends in eda", () => {
    expect(isEdaRoute("/plasmodb/conversation/conv-eda")).toBe(false);
  });

  it("does not match the strategy pane", () => {
    expect(isEdaRoute("/plasmodb/conversation/conv-1/strategy")).toBe(false);
  });
});

// A draft is never redirected away: that case is covered against real queries
// in draftFetches.test.tsx, where the view mounts before the URL rewrite.
describe("ChatShell integration: the rail reads the conversation the view holds", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("ChatView passes the strategy and siteId into the rail StrategyPanel when steps exist", async () => {
    const strategyPanelSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: vi.fn(),
      usePathname: () => "/conversation/with-steps",
      useParams: () => ({
        conversationId: "/conversation/with-steps".split("/").pop(),
      }),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: (opts: { queryKey: readonly unknown[] }) => {
          const key = opts.queryKey.join("/");
          if (key.includes("/detail")) {
            return {
              data: {
                id: "with-steps",
                name: "strat",
                siteId: "plasmodb",
                steps: [{ id: "s1" }],
                rootStepId: "s1",
                recordType: "gene",
                isSaved: false,
                createdAt: "2026-04-17T00:00:00Z",
                updatedAt: "2026-04-17T00:00:00Z",
              },
              isFetched: true,
              isPending: false,
            };
          }
          return { data: [], isFetched: true, isPending: false };
        },
      };
    });
    vi.doMock("./ChatThread", () => ({ ChatThread: () => null }));
    vi.doMock("./branches/BranchSwitcher", () => ({ BranchSwitcher: () => null }));
    vi.doMock("nuqs", () => ({
      useQueryState: () => [null, () => {}],
      parseAsString: {},
    }));
    vi.doMock("./rail/StrategyPanel", () => ({
      StrategyPanel: (props: { strategy: { id: string } | null; siteId: string }) => {
        strategyPanelSpy(props);
        return <div data-testid="strategy-panel" />;
      },
    }));

    const { ChatView } = await import("./ChatView");
    const { render } = await import("@testing-library/react");
    const { useRightRailStore } = await import("@/state/useRightRailStore");

    // Force the rail to be open on the strategy panel for this test.
    useRightRailStore.setState({ openPanel: "strategy" });

    render(<ChatView conversationId="with-steps" />);

    expect(strategyPanelSpy).toHaveBeenCalled();
    const lastCall = strategyPanelSpy.mock.calls.at(-1);
    if (lastCall === undefined) throw new Error("no call");
    const props = lastCall[0] as { strategy: { id: string } | null; siteId: string };
    expect(props.strategy?.id).toBe("with-steps");
    expect(props.siteId).toBe("plasmodb");
  });

  it("ChatView passes a strategy with no steps into the rail StrategyPanel (rail handles empty state)", async () => {
    const strategyPanelSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: vi.fn(),
      usePathname: () => "/conversation/no-steps",
      useParams: () => ({ conversationId: "/conversation/no-steps".split("/").pop() }),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: (opts: { queryKey: readonly unknown[] }) => {
          const key = opts.queryKey.join("/");
          if (key.includes("/detail")) {
            return {
              data: {
                id: "no-steps",
                name: "strat",
                siteId: "plasmodb",
                steps: [],
                rootStepId: null,
                recordType: null,
                isSaved: false,
                createdAt: "2026-04-17T00:00:00Z",
                updatedAt: "2026-04-17T00:00:00Z",
              },
              isFetched: true,
              isPending: false,
            };
          }
          return { data: [], isFetched: true, isPending: false };
        },
      };
    });
    vi.doMock("./ChatThread", () => ({ ChatThread: () => null }));
    vi.doMock("./branches/BranchSwitcher", () => ({ BranchSwitcher: () => null }));
    vi.doMock("nuqs", () => ({
      useQueryState: () => [null, () => {}],
      parseAsString: {},
    }));
    vi.doMock("./rail/StrategyPanel", () => ({
      StrategyPanel: (props: {
        strategy: { steps: unknown[] } | null;
        siteId: string;
      }) => {
        strategyPanelSpy(props);
        return <div data-testid="strategy-panel" />;
      },
    }));

    const { ChatView } = await import("./ChatView");
    const { render } = await import("@testing-library/react");
    const { useRightRailStore } = await import("@/state/useRightRailStore");

    useRightRailStore.setState({ openPanel: "strategy" });

    render(<ChatView conversationId="no-steps" />);

    expect(strategyPanelSpy).toHaveBeenCalled();
    const lastCall = strategyPanelSpy.mock.calls.at(-1);
    if (lastCall === undefined) throw new Error("no call");
    const props = lastCall[0] as {
      strategy: { steps: unknown[] } | null;
      siteId: string;
    };
    expect(props.strategy?.steps).toEqual([]);
  });

  it("ChatView does invoke redirect() when conversationId is an unknown id (not client-generated)", async () => {
    const redirectSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: redirectSpy,
      usePathname: () => "/conversation/stranger",
      useParams: () => ({ conversationId: "/conversation/stranger".split("/").pop() }),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: (opts: { queryKey: readonly unknown[] }) => {
          const key = opts.queryKey.join("/");
          if (key.includes("/detail")) {
            return { data: null, isFetched: true, isPending: false };
          }
          return { data: [], isFetched: true, isPending: false };
        },
      };
    });
    vi.doMock("./ChatThread", () => ({
      ChatThread: () => null,
    }));
    vi.doMock("./branches/BranchSwitcher", () => ({
      BranchSwitcher: () => null,
    }));
    vi.doMock("nuqs", () => ({
      useQueryState: () => [null, () => {}],
      parseAsString: {},
    }));

    const { ChatView } = await import("./ChatView");
    const { render } = await import("@testing-library/react");

    render(<ChatView conversationId="stranger" />);

    // useParams mock omits siteId, so the redirect interpolates an empty
    // segment. The production code prefixes the route with `/${siteId}/`.
    expect(redirectSpy).toHaveBeenCalledWith("//conversation");
  });
});

describe("ChatShell.draftRoute", () => {
  it("names the path alone when the URL asks for no assistant", () => {
    expect(draftRoute("/plasmodb/conversation", null)).toBe("/plasmodb/conversation");
  });

  it("tells two assistants on one path apart", () => {
    expect(draftRoute("/plasmodb/conversation", "site_help")).not.toBe(
      draftRoute("/plasmodb/conversation", null),
    );
  });
});

describe("ChatShell drafts", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("opens a new draft thread when the reader picks another assistant", async () => {
    let search = new URLSearchParams();
    vi.doMock("next/navigation", () => ({
      usePathname: () => "/plasmodb/conversation",
      useSearchParams: () => search,
    }));
    const seen: { conversationId: string; requestedAssistantId: string | null }[] = [];
    vi.doMock("./ChatView", () => ({
      ChatView: (props: {
        conversationId: string;
        requestedAssistantId: string | null;
      }) => {
        seen.push({
          conversationId: props.conversationId,
          requestedAssistantId: props.requestedAssistantId,
        });
        return null;
      },
    }));

    const { ChatShell } = await import("./ChatShell");
    const { render } = await import("@testing-library/react");

    const view = render(<ChatShell />);
    const draft = seen.at(-1);
    if (draft === undefined) throw new Error("ChatView never rendered");
    expect(draft.requestedAssistantId).toBe(null);

    search = new URLSearchParams("assistant=site_help");
    view.rerender(<ChatShell />);

    const picked = seen.at(-1);
    if (picked === undefined) throw new Error("ChatView never rendered");
    expect(picked.requestedAssistantId).toBe("site_help");
    expect(picked.conversationId).not.toBe(draft.conversationId);
  });

  it("keeps the draft thread while the assistant stays the same", async () => {
    const search = new URLSearchParams("assistant=site_help");
    vi.doMock("next/navigation", () => ({
      usePathname: () => "/plasmodb/conversation",
      useSearchParams: () => search,
    }));
    const seen: string[] = [];
    vi.doMock("./ChatView", () => ({
      ChatView: (props: { conversationId: string }) => {
        seen.push(props.conversationId);
        return null;
      },
    }));

    const { ChatShell } = await import("./ChatShell");
    const { render } = await import("@testing-library/react");

    const view = render(<ChatShell />);
    view.rerender(<ChatShell />);

    expect(seen.length).toBeGreaterThan(1);
    expect(new Set(seen).size).toBe(1);
  });
});
