"use client";

import { use } from "react";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { StrategyPage } from "@/features/strategy/page/StrategyPage";

export default function StrategyRoute({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = use(params);
  const { siteId } = useCurrentSite();
  return (
    <StrategyPage siteId={siteId} conversationId={conversationId} focusStepId={null} />
  );
}
