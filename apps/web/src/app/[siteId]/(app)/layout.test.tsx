// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("@/app/hooks/useAutoCollapseSidebar", () => ({
  useAutoCollapseSidebar: () => undefined,
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
      screen.getByLabelText("Switch database - Not responding"),
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
