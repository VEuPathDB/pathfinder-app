// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const pushMock = vi.fn();
const address = vi.hoisted(() => ({ query: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(address.query),
  usePathname: () => "/veupathdb/conversation",
}));
vi.mock("@/lib/api/productEvents", () => ({ recordProductEvent: vi.fn() }));

const session = vi.hoisted(() => ({ authRefreshed: true }));
vi.mock("@/lib/query/hooks/useAuthRefresh", () => ({
  useAuthRefresh: () => ({ authRefreshed: session.authRefreshed }),
}));
vi.mock("@/features/sites/hooks/useSiteTheme", () => ({
  useSiteTheme: () => undefined,
}));
vi.mock("@/app/hooks/useSystemConfig", () => ({
  useSystemConfig: () => ({
    setupRequired: false,
    siteSignInUrl: "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login",
    retry: vi.fn(),
  }),
}));
vi.mock("@/app/hooks/useAutoCollapsePanels", () => ({
  useAutoCollapsePanels: () => undefined,
}));
vi.mock("@/app/hooks/useSidebarResize", () => ({
  useSidebarResize: () => ({
    layoutRef: { current: null },
    sidebarWidth: 280,
    isDragging: false,
    startDragging: vi.fn(),
  }),
}));
vi.mock("@/app/hooks/useModalState", () => ({
  useModalState: () => ({
    settingsOpen: false,
    settingsTab: null,
    openSettings: vi.fn(),
    closeSettings: vi.fn(),
  }),
}));
vi.mock("@/features/sidebar/components/ConversationSidebar", () => ({
  ConversationSidebar: () => <div data-testid="conversation-sidebar" />,
}));
vi.mock("@/features/settings/components/SettingsPage", () => ({
  SettingsPage: () => <div data-testid="settings-page" />,
}));
vi.mock("@/features/help/DataNotice", () => ({
  DataNotice: () => <div data-testid="data-notice" />,
}));

import type { SiteResponse } from "@pathfinder/shared";

import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";

import { sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { chatRoot } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";
import AppShellLayout from "./layout";

/** React reads a thenable that already carries its settled value synchronously. */
function settled<T>(value: T): Promise<T> {
  return Object.assign(Promise.resolve(value), { status: "fulfilled", value });
}

function siteRow(over: Partial<SiteResponse>): SiteResponse {
  return {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://qa.plasmodb.org/plasmo.qa",
    projectId: "PlasmoDB",
    isPortal: false,
    available: true,
    unavailableReason: null,
    ...over,
  };
}

const AVAILABLE_PLASMODB = siteRow({ id: "plasmodb" });
const AVAILABLE_TOXODB = siteRow({
  id: "toxodb",
  name: "ToxoDB",
  displayName: "ToxoDB (Toxoplasma)",
  baseUrl: "https://qa.toxodb.org/toxo.qa",
  projectId: "ToxoDB",
});
const PORTAL_DOWN = siteRow({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
  available: false,
  unavailableReason: "TimeoutError",
});

function holdUnseededReads() {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
}

describe("AppShellLayout site switch", () => {
  beforeEach(holdUnseededReads);
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("sends a site change to that site's chat root", async () => {
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(authStatusOptions("plasmodb").queryKey, {
      signedIn: true,
    });
    queryClient.setQueryData(sitesOptions().queryKey, [
      AVAILABLE_PLASMODB,
      AVAILABLE_TOXODB,
    ]);

    render(
      <Wrapper>
        <AppShellLayout params={settled({ siteId: "plasmodb" })}>
          <div />
        </AppShellLayout>
      </Wrapper>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Switch site" }));
    await userEvent.click(await screen.findByTestId("site-menu-item-toxodb"));
    expect(pushMock.mock.calls).toEqual([[chatRoot("toxodb")]]);
    expect(pushMock).toHaveBeenCalledWith("/toxodb/conversation");
  });

  it("replaces a stored site that the entry flow redirected away from", async () => {
    useSessionStore.setState({ selectedSite: "veupathdb" });
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(authStatusOptions("plasmodb").queryKey, {
      signedIn: false,
    });
    queryClient.setQueryData(sitesOptions().queryKey, [AVAILABLE_PLASMODB]);

    render(
      <Wrapper>
        <AppShellLayout params={settled({ siteId: "plasmodb" })}>
          <div />
        </AppShellLayout>
      </Wrapper>,
    );

    await waitFor(() =>
      expect(useSessionStore.getState().selectedSite).toBe("plasmodb"),
    );
  });
});

function drawSession(signedIn: boolean) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions("plasmodb").queryKey, { signedIn });
  queryClient.setQueryData(sitesOptions().queryKey, [AVAILABLE_PLASMODB]);
  queryClient.setQueryData(getMyQuotaQueryKey(), {
    usedUsd: "1.25",
    limitUsd: "10.00",
    totalTokens: 123456,
    percent: 12.5,
    resetsAt: "2026-10-01T12:00:00Z",
    ownKeyUsd: "0",
    ownKeyTokens: 0,
    ownKeyProviders: [],
  });
  return render(
    <Wrapper>
      <AppShellLayout params={settled({ siteId: "plasmodb" })}>
        <div data-testid="routed-content" />
      </AppShellLayout>
    </Wrapper>,
  );
}

describe("AppShellLayout for a session the website has not signed in", () => {
  beforeEach(holdUnseededReads);
  afterEach(() => {
    cleanup();
    address.query = "";
    vi.unstubAllGlobals();
  });

  it("renders the signed-out notice in place of the content", () => {
    const { container } = drawSession(false);

    expect(screen.getByTestId("signed-out-notice")).toBeVisible();
    expect(screen.getByRole("link", { name: "Sign in to VEuPathDB" })).toHaveAttribute(
      "href",
      "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login?destination=" +
        encodeURIComponent("/pathfinder/veupathdb/conversation"),
    );
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: "Monthly spend" }),
    ).not.toBeInTheDocument();
    expect(container.querySelectorAll("input[type='password']")).toHaveLength(0);
  });

  it("draws the nav rail beside the content once the session is signed in", () => {
    drawSession(true);

    expect(screen.getByRole("link", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByTestId("routed-content")).toBeInTheDocument();
    expect(screen.queryByTestId("signed-out-notice")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Monthly spend" })).toBeInTheDocument();
    expect(screen.getByTestId("data-notice")).toBeInTheDocument();
  });

  it("draws the same shell when the address asks for the embedded layout", () => {
    address.query = "embedded=true";
    drawSession(true);

    expect(screen.getByRole("link", { name: "Conversation" })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Go to conversation" }),
    ).not.toBeInTheDocument();
  });
});

describe("AppShellLayout while the session cookie is minted", () => {
  beforeEach(holdUnseededReads);
  afterEach(() => {
    cleanup();
    session.authRefreshed = true;
    vi.unstubAllGlobals();
  });

  function drawBeforeRefresh() {
    session.authRefreshed = false;
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(authStatusOptions("plasmodb").queryKey, {
      signedIn: true,
    });
    queryClient.setQueryData(sitesOptions().queryKey, [AVAILABLE_PLASMODB]);
    const shell = () => (
      <Wrapper>
        <AppShellLayout params={settled({ siteId: "plasmodb" })}>
          <div data-testid="routed-content" />
        </AppShellLayout>
      </Wrapper>
    );
    const view = render(shell());
    return { rerender: () => view.rerender(shell()) };
  }

  function quotaReads(): string[] {
    return vi
      .mocked(fetch)
      .mock.calls.map(([input]) => String(input))
      .filter((url) => url.includes("/api/v1/me/quota"));
  }

  it("shows the loading screen in place of the routed content", () => {
    drawBeforeRefresh();

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
  });

  it("starts no quota read before the refresh settles", async () => {
    drawBeforeRefresh();
    await act(async () => {});

    expect(quotaReads()).toEqual([]);
  });

  it("mounts the routed content and reads the quota once the refresh settles", async () => {
    const { rerender } = drawBeforeRefresh();

    session.authRefreshed = true;
    rerender();
    await act(async () => {});

    expect(screen.getByTestId("routed-content")).toBeInTheDocument();
    expect(quotaReads()).toHaveLength(1);
  });
});

describe("AppShellLayout framed by the website page", () => {
  beforeEach(holdUnseededReads);
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("posts its path to the website page while the signed-out notice shows", async () => {
    const postMessage = vi.fn();
    vi.stubGlobal("parent", {
      location: { origin: window.location.origin },
      postMessage,
    });

    drawSession(false);
    await act(async () => {});

    expect(screen.getByTestId("signed-out-notice")).toBeVisible();
    expect(postMessage.mock.calls).toEqual([
      [
        { type: "pathfinder:location", path: "/veupathdb/conversation" },
        window.location.origin,
      ],
    ]);
  });
});

describe("AppShellLayout on a site that does not answer", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  function draw(siteId: string) {
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(authStatusOptions(siteId).queryKey, { signedIn: true });
    queryClient.setQueryData(sitesOptions().queryKey, [
      PORTAL_DOWN,
      AVAILABLE_PLASMODB,
    ]);
    return render(
      <Wrapper>
        <AppShellLayout params={settled({ siteId })}>
          <div data-testid="routed-content" />
        </AppShellLayout>
      </Wrapper>,
    );
  }

  it("keeps the nav rail with its marker and replaces the content with the notice", () => {
    draw("veupathdb");

    expect(screen.getByLabelText("Couldn't reach VEuPathDB")).toBeInTheDocument();
    expect(screen.getByTestId("site-trigger-degraded")).toBeInTheDocument();
    expect(screen.getByTestId("site-unavailable-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
  });

  it("draws neither the marker nor the notice on a site that answers", () => {
    draw("plasmodb");

    expect(screen.getByLabelText("Switch site")).toBeInTheDocument();
    expect(screen.queryByTestId("site-trigger-degraded")).not.toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
    expect(screen.getByTestId("routed-content")).toBeInTheDocument();
  });
});

const SITE_UNAVAILABLE = {
  type: "/errors/SITE_UNAVAILABLE",
  title: "Cannot reach the site",
  status: 503,
  detail: "Could not connect to plasmodb (ReadTimeout).",
  code: "SITE_UNAVAILABLE",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Answers the sign-in status with each response in turn and leaves every other read pending. */
function authStatusAnswers(...answers: Array<() => Response>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) => {
      if (!input.includes("/api/v1/veupathdb/auth/status")) {
        return new Promise<Response>(() => {});
      }
      const answer = answers[Math.min(calls.length, answers.length - 1)]!;
      calls.push(input);
      return Promise.resolve(answer());
    }),
  );
  return calls;
}

/** Renders inside an awaited act, so React flushes the render the answer resumes. */
async function drawWithoutStatus() {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, [AVAILABLE_PLASMODB]);
  await act(async () => {
    render(
      <Wrapper>
        <AppShellLayout params={settled({ siteId: "plasmodb" })}>
          <div data-testid="routed-content" />
        </AppShellLayout>
      </Wrapper>,
    );
  });
  return queryClient;
}

describe("AppShellLayout when the sign-in status is refused", () => {
  afterEach(cleanup);

  it("shows the site notice inside the shell for a 503 SITE_UNAVAILABLE", async () => {
    authStatusAnswers(() => json(SITE_UNAVAILABLE, 503));

    await drawWithoutStatus();

    expect(await screen.findByTestId("site-unavailable-notice")).toBeInTheDocument();
    expect(screen.getByLabelText("Switch site")).toBeInTheDocument();
    expect(screen.getByTestId("conversation-sidebar")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
    expect(screen.queryByText("Application error")).not.toBeInTheDocument();
    expect(screen.queryByText("Try another site:")).not.toBeInTheDocument();
  });

  it("keeps the application error for a 500", async () => {
    authStatusAnswers(() =>
      json({ title: "Internal Server Error", status: 500, detail: "boom" }, 500),
    );

    await drawWithoutStatus();

    expect(await screen.findByText("Application error")).toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });

  it("opens the app once a later sign-in status read answers", async () => {
    const calls = authStatusAnswers(
      () => json(SITE_UNAVAILABLE, 503),
      () => json({ signedIn: true }, 200),
    );
    const queryClient = await drawWithoutStatus();
    expect(await screen.findByTestId("site-unavailable-notice")).toBeInTheDocument();

    await act(() =>
      queryClient.refetchQueries({ queryKey: authStatusOptions("plasmodb").queryKey }),
    );

    expect(calls).toHaveLength(2);
    expect(await screen.findByTestId("routed-content")).toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });
});
