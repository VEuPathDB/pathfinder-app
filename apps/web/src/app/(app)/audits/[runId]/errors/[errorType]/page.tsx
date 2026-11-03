"use client";

import { use } from "react";

import { AuditErrorTypePage } from "@/features/audit/AuditErrorTypePage";

export default function AuditErrorTypeRoute({
  params,
}: {
  params: Promise<{ runId: string; errorType: string }>;
}) {
  const { runId, errorType } = use(params);
  return <AuditErrorTypePage runId={runId} errorType={errorType} />;
}
