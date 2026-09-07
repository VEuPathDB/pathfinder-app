// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SiteResponse } from "@pathfinder/shared";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/veupathdb/workbench",
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
vi.mock("@/app/hooks/useModalState", () => ({
  useModalState: () => ({
    showSettings: false,
    settingsTab: null,
    openSettings: vi.fn(),
    closeSettings: vi.fn(),
    setSettingsTab: vi.fn(),
  }),
}));
vi.mock("@/app/components/VeupathdbSignInGate", () => ({
  VeupathdbSignInGate: () => <div data-testid="sign-in-gate" />,
}));
vi.mock("@/app/components/TopBar", () => ({
  TopBar: () => <div data-testid="top-bar" />,
}));
vi.mock("@/features/workbench/components/WorkbenchSidebar", () => ({
  WorkbenchSidebar: () => <div data-testid="workbench-sidebar" />,
}));
vi.mock("@/features/workbench/components/GeneSearchSidebar", () => ({
  GeneSearchSidebar: () => <div data-testid="gene-search-sidebar" />,
}));
vi.mock("@/features/settings/components/SettingsPage", () => ({
  SettingsPage: () => <div data-testid="settings-page" />,
}));
vi.mock("@/features/settings/components/EvalDataNotice", () => ({
  EvalDataNotice: () => <div data-testid="eval-data-notice" />,
}));

import { sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import WorkbenchLayout from "./layout";

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

const PORTAL_DOWN = siteRow({
  id: "veupathdb",
  name: "VEuPathDB",
  displayName: "VEuPathDB Portal (All organisms)",
  isPortal: true,
  available: false,
  unavailableReason: "TimeoutError",
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
    siteRow({ id: "plasmodb" }),
  ]);
  return render(
    <Wrapper>
      <WorkbenchLayout params={settled({ siteId })}>
        <div data-testid="routed-content" />
      </WorkbenchLayout>
    </Wrapper>,
  );
}

afterEach(cleanup);

describe("WorkbenchLayout on a site that does not answer", () => {
  it("keeps the nav rail with its marker and replaces the content with the notice", () => {
    draw("veupathdb");

    expect(
      screen.getByLabelText("Couldn't reach VEuPathDB Portal (All organisms)"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("site-trigger-degraded")).toBeInTheDocument();
    expect(screen.getByTestId("site-unavailable-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("routed-content")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sign-in-gate")).not.toBeInTheDocument();
  });

  it("draws neither the marker nor the notice on a site that answers", () => {
    draw("plasmodb");

    expect(screen.getByLabelText("Switch database")).toBeInTheDocument();
    expect(screen.queryByTestId("site-trigger-degraded")).not.toBeInTheDocument();
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
    expect(screen.getByTestId("routed-content")).toBeInTheDocument();
    expect(screen.getByTestId("sign-in-gate")).toBeInTheDocument();
  });
});
