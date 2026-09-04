"use client";

import { use, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";

import { AppNavRail } from "@/app/components/AppNavRail";
import { AppShellError } from "@/app/components/AppShellError";
import { EmbeddedToolbar } from "@/app/components/EmbeddedToolbar";
import { LoadingScreen } from "@/app/components/LoadingScreen";
import { SetupRequiredScreen } from "@/app/components/SetupRequiredScreen";
import { VeupathdbSignInGate } from "@/app/components/VeupathdbSignInGate";
import { TopBar } from "@/app/components/TopBar";
import { useAuthRefresh } from "@/lib/query/hooks/useAuthRefresh";
import { useAutoCollapseSidebar } from "@/app/hooks/useAutoCollapseSidebar";
import { useModalState } from "@/app/hooks/useModalState";
import { useSidebarResize } from "@/app/hooks/useSidebarResize";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { EvalDataNotice } from "@/features/settings/components/EvalDataNotice";
import { SettingsPage } from "@/features/settings/components/SettingsPage";
import { ConversationSidebar } from "@/features/sidebar/components/ConversationSidebar";
import { useSiteTheme } from "@/features/sites/hooks/useSiteTheme";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { chatRoot } from "@/lib/routes";
import { requiresFullScreenSignIn } from "@/state/useAuthGateStore";
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
    <QueryBoundary loadingFallback={<LoadingScreen />} ErrorFallback={AppShellError}>
      <AppShellInner siteId={siteId}>{children}</AppShellInner>
    </QueryBoundary>
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
  const searchParams = useSearchParams();
  const embedded = searchParams.get("embedded") === "true";

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

  const { data: authStatus } = useSuspenseQuery(authStatusOptions(selectedSite));
  const veupathdbSignedIn = authStatus.signedIn;
  useAuthRefresh(selectedSite);
  useSiteTheme(selectedSite);
  const { setupRequired, retry: retryConfig } = useSystemConfig();

  const { layoutRef, sidebarWidth, isDragging, startDragging } = useSidebarResize();
  const leftCollapsed = useLeftSidebarStore((s) => s.collapsed);
  const toggleLeft = useLeftSidebarStore((s) => s.toggle);
  useAutoCollapseSidebar();
  const modals = useModalState();

  const handleSiteChange = (nextSite: string) => {
    router.push(chatRoot(nextSite));
  };

  if (setupRequired) return <SetupRequiredScreen onRetry={retryConfig} />;

  const forcedSignIn = requiresFullScreenSignIn({
    embedded,
    signedIn: veupathdbSignedIn,
  });
  const signInGate = (
    <VeupathdbSignInGate
      forced={forcedSignIn}
      selectedSite={selectedSite}
      onSiteChange={handleSiteChange}
    />
  );

  if (forcedSignIn) return signInGate;

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      {signInGate}
      {embedded ? (
        <EmbeddedToolbar siteId={selectedSite} onOpenSettings={modals.openSettings} />
      ) : (
        <TopBar selectedSite={selectedSite} />
      )}

      <div ref={layoutRef} className="flex min-h-0 flex-1 overflow-hidden">
        {!embedded && (
          <AppNavRail
            siteId={selectedSite}
            onSiteChange={handleSiteChange}
            onOpenSettings={() => modals.openSettings()}
            onOpenModelSettings={() => modals.openSettings("model")}
            onToggleSidebar={toggleLeft}
            sidebarExpanded={!leftCollapsed}
          />
        )}

        <AnimatePresence initial={false}>
          {!leftCollapsed && (
            <motion.div
              key="sidebar-expanded"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: sidebarWidth, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={
                isDragging
                  ? { duration: 0 }
                  : { type: "spring", stiffness: 380, damping: 36 }
              }
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

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>
      </div>

      <SettingsPage
        open={modals.showSettings}
        onClose={modals.closeSettings}
        siteId={selectedSite}
        tab={modals.settingsTab}
        onTabChange={modals.setSettingsTab}
      />

      <EvalDataNotice />
    </div>
  );
}
