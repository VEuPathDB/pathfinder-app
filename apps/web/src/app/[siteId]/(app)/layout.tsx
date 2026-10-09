"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import { AppNavRail } from "@/app/components/AppNavRail";
import { AppShellError } from "@/app/components/AppShellError";
import { FrameLocationReporter } from "@/app/components/FrameLocationReporter";
import { LoadingScreen } from "@/app/components/LoadingScreen";
import { QueryErrorToasts } from "@/app/components/QueryErrorToasts";
import { SetupRequiredScreen } from "@/app/components/SetupRequiredScreen";
import { SiteAvailabilityGate } from "@/app/components/SiteAvailabilityGate";
import { VeupathdbSignInGate } from "@/app/components/VeupathdbSignInGate";
import { useAuthRefresh } from "@/lib/query/hooks/useAuthRefresh";
import { useAutoCollapsePanels } from "@/app/hooks/useAutoCollapsePanels";
import { useModalState } from "@/app/hooks/useModalState";
import { useSidebarResize } from "@/app/hooks/useSidebarResize";
import { useSiteAccess } from "@/app/hooks/useSiteAccess";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { DataNotice } from "@/features/help/DataNotice";
import { SettingsPage } from "@/features/settings/components/SettingsPage";
import { ConversationSidebar } from "@/features/sidebar/components/ConversationSidebar";
import { useSiteTheme } from "@/features/sites/hooks/useSiteTheme";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { useEntrance } from "@/lib/motion";
import { chatRoot } from "@/lib/routes";
import { useLeftSidebarStore } from "@/state/useRightRailStore";
import { useSessionStore } from "@/state/useSessionStore";

export default function AppShellLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ siteId: string }>;
}) {
  const { siteId } = use(params);
  return (
    <>
      <FrameLocationReporter />
      <QueryBoundary loadingFallback={<LoadingScreen />} ErrorFallback={AppShellError}>
        <AppShellInner siteId={siteId}>{children}</AppShellInner>
      </QueryBoundary>
    </>
  );
}

function AppShellInner({
  siteId,
  children,
}: {
  siteId: string;
  children: React.ReactNode;
}) {
  const router = useRouter();

  const selectedSite = siteId;

  // URL is the source of truth; mirror it into the session store so
  // downstream consumers that still read from the store see the current site.
  // Defer the cross-store write to a microtask so React's "setState during
  // render" warning doesn't fire (the store update would re-render any
  // subscriber if done synchronously here).
  const [syncedSite, setSyncedSite] = useState<string | null>(null);
  if (syncedSite !== siteId) {
    setSyncedSite(siteId);
    queueMicrotask(() => {
      useSessionStore.setState({ selectedSite: siteId });
    });
  }

  const access = useSiteAccess(selectedSite);
  const { authRefreshed } = useAuthRefresh(selectedSite);
  useSiteTheme(selectedSite);
  const { setupRequired, retry: retryConfig } = useSystemConfig();

  const { layoutRef, sidebarWidth, isDragging, startDragging } = useSidebarResize();
  const leftCollapsed = useLeftSidebarStore((s) => s.collapsed);
  const toggleLeft = useLeftSidebarStore((s) => s.toggle);
  useAutoCollapsePanels();
  const modals = useModalState();
  const sidebarEntrance = useEntrance({
    initial: { width: 0, opacity: 0 },
    exit: { width: 0, opacity: 0 },
    transition: isDragging
      ? { duration: 0 }
      : { type: "spring", stiffness: 380, damping: 36 },
  });

  const handleSiteChange = (nextSite: string) => {
    router.push(chatRoot(nextSite));
  };

  if (setupRequired) return <SetupRequiredScreen onRetry={retryConfig} />;
  if (access.kind === "pending") return <LoadingScreen />;

  // A site PathFinder cannot reach cannot authenticate anyone, so the notice
  // takes the sign-in prompt's place.
  const siteDown = access.kind === "down";
  const forcedSignIn = access.kind === "up" && !access.signedIn;
  const signInGate = siteDown ? null : <VeupathdbSignInGate forced={forcedSignIn} />;

  if (forcedSignIn) {
    return (
      <>
        <QueryErrorToasts />
        {signInGate}
      </>
    );
  }
  if (access.kind === "up" && !authRefreshed) return <LoadingScreen />;

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <QueryErrorToasts />
      {signInGate}

      <div ref={layoutRef} className="flex min-h-0 flex-1 overflow-hidden">
        <AppNavRail
          siteId={selectedSite}
          onSiteChange={handleSiteChange}
          onOpenSettings={() => modals.openSettings()}
          onOpenModelSettings={() => modals.openSettings("model")}
          onToggleSidebar={toggleLeft}
          sidebarExpanded={!leftCollapsed}
        />

        <AnimatePresence initial={false}>
          {!leftCollapsed && (
            <motion.div
              key="sidebar-expanded"
              {...sidebarEntrance}
              animate={{ width: sidebarWidth, opacity: 1 }}
              className="h-full shrink-0 overflow-hidden border-r border-border bg-sidebar"
            >
              <div style={{ width: sidebarWidth }} className="h-full">
                <ConversationSidebar siteId={selectedSite} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!leftCollapsed && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            onMouseDown={startDragging}
            className="w-1 cursor-col-resize bg-muted transition-colors duration-150 hover:bg-primary/20"
          />
        )}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <SiteAvailabilityGate siteId={selectedSite} down={siteDown}>
            {children}
          </SiteAvailabilityGate>
        </div>
      </div>

      <SettingsPage
        open={modals.showSettings}
        onClose={modals.closeSettings}
        siteId={selectedSite}
        tab={modals.settingsTab}
        onTabChange={modals.setSettingsTab}
      />

      <DataNotice />
    </div>
  );
}
