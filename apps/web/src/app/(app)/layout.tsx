"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import { AppNavRail } from "@/app/components/AppNavRail";
import { AppShellError } from "@/app/components/AppShellError";
import { ConversationElsewhereNotice } from "@/app/components/ConversationElsewhereNotice";
import { FrameLocationReporter } from "@/app/components/FrameLocationReporter";
import { LoadingScreen } from "@/app/components/LoadingScreen";
import { QueryErrorToasts } from "@/app/components/QueryErrorToasts";
import { SetupRequiredScreen } from "@/app/components/SetupRequiredScreen";
import { SiteAvailabilityGate } from "@/app/components/SiteAvailabilityGate";
import { SystemReadyGate } from "@/app/components/SystemReadyGate";
import { VeupathdbSignInGate } from "@/app/components/VeupathdbSignInGate";
import { useAutoCollapsePanels } from "@/app/hooks/useAutoCollapsePanels";
import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { useModalState } from "@/app/hooks/useModalState";
import { useSidebarResize } from "@/app/hooks/useSidebarResize";
import { useSiteAccess } from "@/app/hooks/useSiteAccess";
import { useSitePages } from "@/app/hooks/useSitePages";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { useWebsitePage } from "@/app/hooks/useWebsitePage";
import { DataNotice } from "@/features/help/DataNotice";
import { SettingsPage } from "@/features/settings/components/SettingsPage";
import { ConversationSidebar } from "@/features/sidebar/components/ConversationSidebar";
import { useSiteTheme } from "@/features/sites/hooks/useSiteTheme";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { useEntrance } from "@/lib/motion";
import { RailFoot } from "@/lib/components/RailFoot";
import { chatRoot, conversationIdFromPath, isChatPath } from "@/lib/routes";
import { useLeftSidebarStore } from "@/state/useRightRailStore";
import { useSessionStore } from "@/state/useSessionStore";

export default function AppShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <SystemReadyGate>
      <FrameLocationReporter />
      <QueryBoundary loadingFallback={<LoadingScreen />} ErrorFallback={AppShellError}>
        <AppShellInner>{children}</AppShellInner>
      </QueryBoundary>
    </SystemReadyGate>
  );
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const conversationId = conversationIdFromPath(pathname);
  const { siteId: selectedSite, locked, conversationSite } = useCurrentSite();
  const elsewhereSite =
    locked !== undefined && conversationSite !== locked.id ? conversationSite : null;

  // Mirror the resolved site into the session store, where readers outside
  // the route read it, and let a conversation opened on a website with a
  // picker become the picked site. A microtask keeps the cross-store write
  // out of render.
  const [syncedSite, setSyncedSite] = useState<string | null>(null);
  if (syncedSite !== selectedSite) {
    setSyncedSite(selectedSite);
    queueMicrotask(() => {
      useSessionStore.setState({ selectedSite });
      if (locked === undefined) useSessionStore.getState().setPickedSite(selectedSite);
    });
  }

  const access = useSiteAccess(selectedSite);
  useSiteTheme(selectedSite);
  const { setupRequired, retry: retryConfig } = useSystemConfig();
  useWebsitePage(useSitePages().pageUrl);

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

  const handleSiteChange = () => {
    router.push(chatRoot());
  };

  if (setupRequired) return <SetupRequiredScreen onRetry={retryConfig} />;
  if (access.kind === "pending") return <LoadingScreen />;

  // A site PathFinder cannot reach cannot authenticate anyone, so the notice
  // takes the sign-in prompt's place.
  const siteDown = access.kind === "down";
  const showsElsewhere = elsewhereSite !== null && conversationId !== null;
  const rightRailShown = isChatPath(pathname) && !siteDown && !showsElsewhere;
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
  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <QueryErrorToasts />
      {signInGate}

      <div ref={layoutRef} className="flex min-h-0 flex-1 overflow-hidden">
        <AppNavRail
          siteId={selectedSite}
          siteSwitchable={locked === undefined}
          onSiteChange={handleSiteChange}
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
            {showsElsewhere ? (
              <ConversationElsewhereNotice
                siteId={elsewhereSite}
                conversationId={conversationId}
              />
            ) : (
              children
            )}
          </SiteAvailabilityGate>
        </div>

        {!rightRailShown && (
          <aside
            aria-label="Help and settings"
            className="flex h-full w-11 shrink-0 flex-col items-center border-l border-border bg-sidebar py-2"
          >
            <RailFoot onOpenSettings={() => modals.openSettings()} />
          </aside>
        )}
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
