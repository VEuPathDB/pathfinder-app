// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/veupathdb/conversation",
}));

vi.mock("@/lib/query/hooks/useAuthRefresh", () => ({
  useAuthRefresh: () => undefined,
}));
vi.mock("@/features/sites/hooks/useSiteTheme", () => ({
  useSiteTheme: () => undefined,
}));
vi.mock("@/app/hooks/useSystemConfig", () => ({
  useSystemConfig: () => ({ setupRequired: false, retry: vi.fn() }),
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
vi.mock("@/app/components/VeupathdbSignInGate", () => ({
  VeupathdbSignInGate: ({ onSiteChange }: { onSiteChange: (site: string) => void }) => (
    <button type="button" onClick={() => onSiteChange("toxodb")}>
      Switch site
    </button>
  ),
}));
vi.mock("@/app/components/TopBar", () => ({
  TopBar: () => <div data-testid="top-bar" />,
}));
vi.mock("@/features/sidebar/components/ConversationSidebar", () => ({
  ConversationSidebar: () => <div data-testid="conversation-sidebar" />,
}));
vi.mock("@/features/settings/components/SettingsPage", () => ({
  SettingsPage: () => <div data-testid="settings-page" />,
}));
vi.mock("@/features/settings/components/EvalDataNotice", () => ({
  EvalDataNotice: () => <div data-testid="eval-data-notice" />,
}));

import type { SiteResponse } from "@pathfinder/shared";

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
    baseUrl: "https://plasmodb.org/plasmo",
    projectId: "PlasmoDB",
    isPortal: false,
    available: true,
    unavailableReason: null,
    ...over,
  };
}

const AVAILABLE_PLASMODB = siteRow({ id: "plasmodb" });
const PORTAL_DOWN = siteRow({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
  available: false,
  unavailableReason: "TimeoutError",
});

describe("AppShellLayout site switch", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  it("sends a site change to that site's chat root", async () => {
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

    await userEvent.click(screen.getByRole("button", { name: "Switch site" }));
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

describe("AppShellLayout on a site that does not answer", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  function draw(siteId: string) {
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(authStatusOptions(siteId).queryKey, {
      signedIn: true,
      name: "Researcher",
      email: "researcher@upenn.edu",
    });
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

    expect(
      screen.getByLabelText("Couldn't reach VEuPathDB Portal (All organisms)"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("site-trigger-degraded")).toBeInTheDocument();
    expect(screen.getByTestId("site-unavailable-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
  });

  it("draws neither the marker nor the notice on a site that answers", () => {
    draw("plasmodb");

    expect(screen.getByLabelText("Switch database")).toBeInTheDocument();
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
    expect(screen.getByLabelText("Switch database")).toBeInTheDocument();
    expect(screen.getByTestId("conversation-sidebar")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
    expect(screen.queryByText("Application error")).not.toBeInTheDocument();
    expect(screen.queryByText("Try another database:")).not.toBeInTheDocument();
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
