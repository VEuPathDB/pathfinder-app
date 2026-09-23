"use client";

import { usePrefetchQuery, useQuery } from "@tanstack/react-query";
import { Suspense, useState } from "react";
import { useInterval } from "usehooks-ts";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";
import { systemReadyQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemReady";

import { sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { BusyWorkerBanner } from "./BusyWorkerBanner";
import { LoadingScreen } from "./LoadingScreen";
import { STARTUP_GRACE_MS, StartupScreen, startupStatus } from "./StartupScreen";

export function SystemReadyGate({
  siteId,
  children,
}: {
  siteId: string;
  children: React.ReactNode;
}) {
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const { data, isError } = useQuery({
    ...systemReadyQueryOptions(),
    retry: false,
    refetchInterval: (query) => (query.state.data?.ready === true ? false : 2000),
  });

  const ready = data?.ready === true;
  // Heartbeat so the grace window can elapse even if a readiness request is
  // stuck in-flight (e.g. the DB is unreachable and the query never resolves).
  useInterval(() => setNow(Date.now()), ready ? null : 1000);

  const app = (
    <>
      <AppShellPrefetch siteId={siteId} />
      <Suspense fallback={<LoadingScreen />}>{children}</Suspense>
    </>
  );

  if (ready) return app;

  const status = startupStatus({
    data,
    isError,
    elapsedMs: now - mountedAt,
    graceMs: STARTUP_GRACE_MS,
  });

  if (status.kind === "busy-worker") {
    return (
      <div className="flex h-full flex-col">
        <BusyWorkerBanner />
        <div className="min-h-0 flex-1">{app}</div>
      </div>
    );
  }

  return <StartupScreen status={status} />;
}

/** Starts the reads every app shell suspends on while the shell code still loads. */
function AppShellPrefetch({ siteId }: { siteId: string }) {
  usePrefetchQuery(sitesOptions());
  usePrefetchQuery(listModelsQueryOptions());
  usePrefetchQuery(authStatusOptions(siteId));
  return null;
}
