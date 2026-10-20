"use client";

import { use } from "react";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { EdaWorkbench } from "@/features/eda/EdaWorkbench";

export default function EdaRoute({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = use(params);
  const { siteId } = useCurrentSite();
  return <EdaWorkbench siteId={siteId} conversationId={conversationId} />;
}
