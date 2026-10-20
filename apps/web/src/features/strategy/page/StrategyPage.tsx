"use client";

import { redirect } from "next/navigation";

import { Spinner } from "@/components/ui/spinner";
import { useStrategyQuery } from "@/lib/api/strategy";
import { chatRoot } from "@/lib/routes";
import { StrategyGraph } from "@/features/strategy/graph/components/StrategyGraph";

interface StrategyPageProps {
  siteId: string;
  conversationId: string;
  /** When set, the editor sheet auto-opens focused on this step. */
  focusStepId: string | null;
}

export function StrategyPage({
  siteId,
  conversationId,
  focusStepId,
}: StrategyPageProps) {
  const detailQuery = useStrategyQuery(conversationId);

  if (detailQuery.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-card">
        <Spinner className="size-5" />
      </div>
    );
  }

  const strategy = detailQuery.data ?? null;

  if (strategy === null) {
    redirect(chatRoot());
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      <StrategyGraph
        strategy={strategy}
        siteId={siteId}
        conversationId={conversationId}
        showTopbar
        focusStepId={focusStepId}
      />
    </div>
  );
}
