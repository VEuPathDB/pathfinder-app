/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createSuspenseWrapper } from "@/lib/query/testing";
import { chatUrl } from "@/lib/routes";

const routerPushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPushMock }),
  usePathname: () => "/plasmodb/conversation",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@pathfinder/shared/generated/hooks/useOpenStrategy", () => ({
  openStrategy: vi.fn(() => Promise.resolve({ conversationId: "conv-9" })),
}));

import { openStrategy } from "@pathfinder/shared/generated/hooks/useOpenStrategy";
import { OpenWdkStrategyDialog } from "./OpenWdkStrategyDialog";

const mockOpenStrategy = vi.mocked(openStrategy);

const LISTED = [
  {
    wdkStrategyId: 214626640,
    name: "secreted proteins",
    estimatedSize: 1043,
    isSaved: true,
    lastModified: "2026-09-14T17:31:02",
  },
  {
    wdkStrategyId: 214626001,
    name: "gametocyte markers",
    estimatedSize: 132,
    isSaved: false,
    lastModified: "2026-09-10T08:00:00",
  },
];

let answer: unknown[] = LISTED;
const reads: string[] = [];
const server = setupServer(
  http.get("http://localhost:3000/api/v1/sites/plasmodb/strategies", ({ request }) => {
    reads.push(request.url);
    return HttpResponse.json(answer);
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  answer = LISTED;
  reads.length = 0;
  routerPushMock.mockClear();
  mockOpenStrategy.mockClear();
});
afterAll(() => server.close());

function site(id: string, name: string, baseUrl: string): SiteResponse {
  return {
    id,
    name,
    displayName: name,
    baseUrl,
    projectId: name,
    isPortal: false,
    available: true,
    unavailableReason: null,
  };
}

const SITES: SiteResponse[] = [
  site("plasmodb", "PlasmoDB", "https://plasmodb.org/plasmo/service"),
  site("toxodb", "ToxoDB", "https://toxodb.org/toxo/service"),
];

function renderDialog(open = true, siteId = "plasmodb") {
  const { queryClient, Wrapper } = createSuspenseWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, SITES);
  return render(
    <Wrapper>
      <OpenWdkStrategyDialog open={open} onOpenChange={() => {}} siteId={siteId} />
    </Wrapper>,
  );
}

describe("the VEuPathDB strategy import dialog", () => {
  it("offers the account's strategies in the order the route answers", async () => {
    renderDialog();

    const first = await screen.findByTestId("open-wdk-strategy-pick-214626640");
    expect(first).toHaveTextContent("secreted proteins");
    expect(first).toHaveTextContent("1,043 results");
    expect(first).toHaveTextContent("Saved");

    const rows = screen.getAllByTestId(/^open-wdk-strategy-pick-/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "open-wdk-strategy-pick-214626640",
      "open-wdk-strategy-pick-214626001",
    ]);

    const second = within(screen.getByTestId("open-wdk-strategy-pick-214626001"));
    expect(second.getByText(/132 results/)).toBeVisible();
    expect(second.queryByText(/Saved/)).toBeNull();
    expect([...new Set(reads)]).toEqual([
      "http://localhost:3000/api/v1/sites/plasmodb/strategies",
    ]);
  });

  it("asks for no listing while the dialog is closed", async () => {
    renderDialog(false);

    await waitFor(() =>
      expect(screen.queryByTestId("open-wdk-strategy-dialog")).toBeNull(),
    );
    expect(reads).toEqual([]);
  });

  it("opens the strategy the researcher picks from the list", async () => {
    renderDialog();

    await userEvent.click(
      await screen.findByTestId("open-wdk-strategy-pick-214626001"),
    );
    await userEvent.click(screen.getByTestId("open-wdk-strategy-confirm"));

    await waitFor(() =>
      expect(mockOpenStrategy.mock.calls).toEqual([
        [{ siteId: "plasmodb", wdkStrategyId: 214626001 }],
      ]),
    );
    expect(routerPushMock.mock.calls).toEqual([[chatUrl("plasmodb", "conv-9")]]);
  });

  it("narrows the list to the strategies whose name the filter matches", async () => {
    renderDialog();
    await screen.findByTestId("open-wdk-strategy-pick-214626640");

    await userEvent.type(screen.getByTestId("open-wdk-strategy-filter"), "gametocyte");

    expect(screen.queryByTestId("open-wdk-strategy-pick-214626640")).toBeNull();
    expect(screen.getByTestId("open-wdk-strategy-pick-214626001")).toBeInTheDocument();
  });

  it("still takes a pasted link when the account holds no strategy", async () => {
    answer = [];
    renderDialog();

    expect(await screen.findByText("No strategies on PlasmoDB yet.")).toBeVisible();

    await userEvent.type(
      screen.getByTestId("open-wdk-strategy-input"),
      "https://plasmodb.org/plasmo/app/workspace/strategies/214626640",
    );
    await userEvent.click(screen.getByTestId("open-wdk-strategy-confirm"));

    await waitFor(() =>
      expect(mockOpenStrategy.mock.calls).toEqual([
        [{ siteId: "plasmodb", wdkStrategyId: 214626640 }],
      ]),
    );
  });

  it("shows an example link on the site the researcher works on", async () => {
    renderDialog(true, "toxodb");

    expect(await screen.findByTestId("open-wdk-strategy-input")).toHaveAttribute(
      "placeholder",
      "https://toxodb.org/toxo/app/workspace/strategies/214626640",
    );
  });

  it("refuses a link another site serves and names that site", async () => {
    renderDialog();
    await screen.findByTestId("open-wdk-strategy-pick-214626640");

    await userEvent.type(
      screen.getByTestId("open-wdk-strategy-input"),
      "https://toxodb.org/toxo/app/workspace/strategies/330528343",
    );

    expect(screen.getByTestId("open-wdk-strategy-notice")).toHaveTextContent(
      "That link names a ToxoDB strategy. Switch to ToxoDB to open it.",
    );
    expect(screen.getByTestId("open-wdk-strategy-confirm")).toBeDisabled();
    expect(mockOpenStrategy.mock.calls).toEqual([]);
  });

  it("refuses a link from a host this deployment does not serve", async () => {
    renderDialog();
    await screen.findByTestId("open-wdk-strategy-pick-214626640");

    await userEvent.type(
      screen.getByTestId("open-wdk-strategy-input"),
      "https://beta.plasmodb.org/plasmo/app/workspace/strategies/7",
    );

    expect(screen.getByTestId("open-wdk-strategy-notice")).toHaveTextContent(
      "PathFinder has no site at beta.plasmodb.org.",
    );
    expect(screen.getByTestId("open-wdk-strategy-confirm")).toBeDisabled();
  });

  it("draws no notice for a link this site serves", async () => {
    renderDialog();
    await screen.findByTestId("open-wdk-strategy-pick-214626640");

    await userEvent.type(
      screen.getByTestId("open-wdk-strategy-input"),
      "https://plasmodb.org/plasmo/app/workspace/strategies/214626640",
    );

    expect(screen.queryByTestId("open-wdk-strategy-notice")).toBeNull();
    expect(screen.getByTestId("open-wdk-strategy-confirm")).toBeEnabled();
  });

  it("says so when the listing cannot be read, and keeps the paste path", async () => {
    server.use(
      http.get("http://localhost:3000/api/v1/sites/plasmodb/strategies", () =>
        HttpResponse.json({ detail: "no" }, { status: 503 }),
      ),
    );
    renderDialog();

    expect(
      await screen.findByText("Your PlasmoDB strategies could not be read."),
    ).toBeVisible();
    expect(screen.getByTestId("open-wdk-strategy-input")).toBeEnabled();
  });
});
