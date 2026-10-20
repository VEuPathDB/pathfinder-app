"use client";

import { use } from "react";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { StrategyPage } from "@/features/strategy/page/StrategyPage";

export default function StrategyStepRoute({
  params,
}: {
  params: Promise<{ conversationId: string; stepId: string }>;
}) {
  const { conversationId, stepId } = use(params);
  const { siteId } = useCurrentSite();
  return (
    <StrategyPage
      siteId={siteId}
      conversationId={conversationId}
      focusStepId={stepId}
    />
  );
}
