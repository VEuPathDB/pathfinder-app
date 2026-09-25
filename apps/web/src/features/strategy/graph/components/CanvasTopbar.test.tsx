// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Strategy } from "@pathfinder/shared";
import { createTestWrapper } from "@/lib/query/testing";
import { chatUrl, strategyCanvasUrl } from "@/lib/routes";
import { useFirstMessageStore } from "@/state/useFirstMessageStore";
import { CanvasTopbar } from "./CanvasTopbar";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/conversation/conv-1/strategy",
}));

const pushStrategyMock = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/usePushStrategy", () => ({
  pushStrategy: pushStrategyMock.mockImplementation(
    async (_id: string, body: { name: string }) => ({ ...STRATEGY, name: body.name }),
  ),
}));

vi.mock("@pathfinder/shared/generated/hooks/useComputeStepCounts", () => ({
  computeStepCounts: vi.fn(async () => ({ counts: {} })),
}));

const STRATEGY: Strategy = {
  id: "conv-1",
  name: "My strategy",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_1",
      kind: "search",
      displayName: "Genes by taxon",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
  ],
  rootStepId: "step_1",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

describe("CanvasTopbar", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  it("renders strategy name in an editable input", () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="idle"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    const input = screen.getByLabelText<HTMLInputElement>("Strategy name");
    expect(input.value).toBe("My strategy");
  });

  it("Back button routes to conversation parent", () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="idle"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    fireEvent.click(screen.getByRole("button", { name: /back to conversation/i }));
    expect(pushMock).toHaveBeenCalledWith(chatUrl("plasmodb", "conv-1"));
  });

  it("renders sync status reflecting saving / error / idle", () => {
    const { Wrapper } = createTestWrapper();
    const { rerender } = render(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="saving"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    expect(screen.getByText(/Saving/i)).toBeTruthy();

    rerender(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="error"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    expect(screen.getByRole("button", { name: /failed.*retry/i })).toBeTruthy();

    rerender(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="idle"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    expect(screen.getByText(/^Saved$/i)).toBeTruthy();
  });

  it("copies the canvas URL the route builder produces", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <CanvasTopbar
          strategy={STRATEGY}
          conversationId="conv-1"
          syncState="idle"
          onRetry={() => {}}
        />
      </Wrapper>,
    );
    await userEvent.click(screen.getByLabelText("More strategy actions"));
    await userEvent.click(await screen.findByText("Copy strategy URL"));
    expect(writeText).toHaveBeenCalledWith(
      `${window.location.origin}${strategyCanvasUrl("plasmodb", "conv-1")}`,
    );
  });
});

describe("the link to the host site", () => {
  afterEach(cleanup);

  const withWdk = {
    ...STRATEGY,
    wdkStrategyId: 330528343,
    wdkUrl: "https://plasmodb.org/plasmo/app/workspace/strategies/330528343",
  } as Strategy;

  function renderTopbar(strategy: Strategy) {
    const { Wrapper } = createTestWrapper();
    return render(
      <Wrapper>
        <CanvasTopbar
          strategy={strategy}
          conversationId="conv-1"
          syncState="idle"
          onRetry={vi.fn()}
        />
      </Wrapper>,
    );
  }

  // The canvas is the full editor. Reaching the strategy on the host site
  // should not mean going back to the chat rail.
  it("sits in the top bar", () => {
    renderTopbar(withWdk);

    expect(screen.getByTestId("canvas-topbar")).toContainElement(
      screen.getByRole("link", { name: "Open in PlasmoDB" }),
    );
  });

  it("points at the strategy on the host site", () => {
    renderTopbar(withWdk);

    expect(
      screen.getByRole("link", { name: "Open in PlasmoDB" }).getAttribute("href"),
    ).toBe(withWdk.wdkUrl);
  });

  it("says it opens the strategy on the site it belongs to", () => {
    renderTopbar(withWdk);

    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute("aria-label", "Open in PlasmoDB");
    expect(link.textContent).toBe("Open in PlasmoDB");
  });

  it("opens in a new tab without leaking the referrer", () => {
    renderTopbar(withWdk);
    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });

    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("sits next to the actions menu", () => {
    renderTopbar(withWdk);
    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });
    const menu = screen.getByLabelText("More strategy actions");

    expect(link.parentElement).toBe(menu.parentElement);
  });

  it("offers no link before the strategy reaches WDK", () => {
    renderTopbar(STRATEGY);

    expect(screen.queryAllByRole("link", { name: /^Open in / })).toHaveLength(0);
  });
});

describe("the name of a strategy whose conversation has no title yet", () => {
  afterEach(() => {
    cleanup();
    useFirstMessageStore.setState({ byConversation: {} });
    pushStrategyMock.mockClear();
  });

  function renderUntitled() {
    useFirstMessageStore
      .getState()
      .rememberFirstMessage("conv-1", [
        { id: "u1", role: "user", parts: [{ type: "text", text: "find kinases" }] },
      ]);
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <CanvasTopbar
          strategy={{ ...STRATEGY, name: "" }}
          conversationId="conv-1"
          syncState="idle"
          onRetry={vi.fn()}
        />
      </Wrapper>,
    );
  }

  it("shows the first message in the name field and saves nothing", async () => {
    renderUntitled();

    const input = screen.getByLabelText<HTMLInputElement>("Strategy name");
    expect([input.value, input.placeholder]).toEqual(["", "find kinases"]);
    await userEvent.click(input);
    await userEvent.tab();
    expect(pushStrategyMock.mock.calls).toEqual([]);
  });

  it("names the first message in the delete confirmation", async () => {
    renderUntitled();

    await userEvent.click(screen.getByLabelText("More strategy actions"));
    await userEvent.click(await screen.findByText("Delete strategy"));

    expect(await screen.findByRole("dialog")).toHaveTextContent("find kinases");
  });
});
