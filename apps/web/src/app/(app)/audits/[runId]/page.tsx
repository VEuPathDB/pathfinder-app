"use client";

import { use } from "react";

import { AuditRunPage } from "@/features/audit/AuditRunPage";

export default function AuditRunRoute({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  return <AuditRunPage runId={runId} />;
}
