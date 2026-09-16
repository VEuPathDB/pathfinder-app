"use client";

import { type ReactNode, use } from "react";
import { useRouter } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import { useSessionStore } from "@/state/useSessionStore";
import { AppNavRail } from "@/app/components/AppNavRail";
import { TopBar } from "@/app/components/TopBar";
import { VeupathdbSignInGate } from "@/app/components/VeupathdbSignInGate";
import { LoadingScreen } from "@/app/components/LoadingScreen";
import { QueryErrorToasts } from "@/app/components/QueryErrorToasts";
import { EvalDataNotice } from "@/features/settings/components/EvalDataNotice";
import { SettingsPage } from "@/features/settings/components/SettingsPage";
import { useAuthRefresh } from "@/lib/query/hooks/useAuthRefresh";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { useModalState } from "@/app/hooks/useModalState";
import { useWorkbenchSidebarLayout } from "@/app/hooks/useWorkbenchSidebarLayout";
import { SetupRequiredScreen } from "@/app/components/SetupRequiredScreen";
import { SiteAvailabilityGate } from "@/app/components/SiteAvailabilityGate";
import { useSiteTheme } from "@/features/sites/hooks/useSiteTheme";
import { WorkbenchSidebar } from "@/features/workbench/components/WorkbenchSidebar";
import { GeneSearchSidebar } from "@/features/workbench/components/GeneSearchSidebar";
import { SidebarEdgeTab } from "@/features/workbench/components/SidebarEdgeTab";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { requiresFullScreenSignIn } from "@/state/useAuthGateStore";
import { sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { siteIsDown } from "@/lib/sites/availability";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { AppShellError } from "@/app/components/AppShellError";
import { Search } from "lucide-react";

export default function WorkbenchLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ siteId: string }>;
}) {
  const { siteId } = use(params);
  return (
    <QueryBoundary loadingFallback={<LoadingScreen />} ErrorFallback={AppShellError}>
      <WorkbenchLayoutInner siteId={siteId}>{children}</WorkbenchLayoutInner>
    </QueryBoundary>
  );
}

function WorkbenchLayoutInner({
  siteId,
  children,
}: {
  siteId: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const storedSite = useSessionStore((s) => s.selectedSite);
  const selectedSite = siteId;

  if (storedSite !== siteId) {
    useSessionStore.setState({ selectedSite: siteId });
  }
  const { data: authStatus } = useSuspenseQuery(authStatusOptions(selectedSite));
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const veupathdbSignedIn = authStatus.signedIn;
  const { setupRequired, retry: retryConfig } = useSystemConfig();
  useSiteTheme(selectedSite);
  useAuthRefresh(selectedSite);

  const handleSiteChange = (nextSite: string) => {
    router.push(`/${nextSite}/workbench`);
  };

  const modals = useModalState();
  const sidebarWidth = useWorkbenchSidebarLayout();
  const { geneSearchOpen, toggleGeneSearch, leftSidebarOpen, toggleLeftSidebar } =
    useWorkbenchStore(
      useShallow((s) => ({
        geneSearchOpen: s.geneSearchOpen,
        toggleGeneSearch: s.toggleGeneSearch,
        leftSidebarOpen: s.leftSidebarOpen,
        toggleLeftSidebar: s.toggleLeftSidebar,
      })),
    );

  if (setupRequired) return <SetupRequiredScreen onRetry={retryConfig} />;

  // A site PathFinder cannot reach cannot authenticate anyone, so the notice
  // takes the sign-in prompt's place.
  const siteDown = siteIsDown(sites, selectedSite);
  const forcedSignIn =
    !siteDown &&
    requiresFullScreenSignIn({ embedded: false, signedIn: veupathdbSignedIn });

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <QueryErrorToasts />
      {!siteDown && (
        <VeupathdbSignInGate
          forced={forcedSignIn}
          selectedSite={selectedSite}
          onSiteChange={handleSiteChange}
        />
      )}
      <TopBar selectedSite={selectedSite} />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <AppNavRail
          siteId={selectedSite}
          onSiteChange={handleSiteChange}
          onOpenSettings={() => modals.openSettings()}
          onOpenModelSettings={() => modals.openSettings("model")}
          onToggleSidebar={toggleLeftSidebar}
          sidebarExpanded={leftSidebarOpen}
        />
        {leftSidebarOpen && (
          <div
            data-testid="workbench-sidebar-panel"
            style={{ width: sidebarWidth }}
            className="shrink-0 border-r border-border bg-sidebar"
          >
            <WorkbenchSidebar onCollapse={toggleLeftSidebar} />
          </div>
        )}

        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-card">
          <SiteAvailabilityGate siteId={selectedSite}>{children}</SiteAvailabilityGate>
        </div>

        {geneSearchOpen ? (
          <div className="w-80 shrink-0 border-l border-border bg-sidebar">
            <GeneSearchSidebar onCollapse={toggleGeneSearch} />
          </div>
        ) : (
          <SidebarEdgeTab
            side="right"
            label="Gene Search"
            icon={<Search className="h-4 w-4" />}
            onClick={toggleGeneSearch}
          />
        )}
      </div>

      <SettingsPage
        open={modals.showSettings}
        onClose={modals.closeSettings}
        siteId={selectedSite}
        tab={modals.settingsTab}
        onTabChange={modals.setSettingsTab}
      />

      {!forcedSignIn && <EvalDataNotice />}
    </div>
  );
}
