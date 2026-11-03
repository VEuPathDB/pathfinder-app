"use client";

import { use } from "react";

import { AuditFindingPage } from "@/features/audit/AuditFindingPage";

export default function AuditFindingRoute({
  params,
}: {
  params: Promise<{ runId: string; findingId: string }>;
}) {
  const { runId, findingId } = use(params);
  return <AuditFindingPage runId={runId} findingId={findingId} />;
}
