import { z } from "zod";

import { auditFindingUrl, auditRunUrl } from "@/lib/routes";

import type { TraceRowView } from "./traceTypes";

export interface AuditReportLink {
  href: string;
  label: string;
}

const REPORT = "Open the audit report";
const FINDING = "Open the finding";

const ANSWERED: ReadonlySet<TraceRowView["status"]> = new Set(["ok", "empty", "warn"]);

const startedSchema = z.object({ answer: z.object({ run_id: z.uuid() }) });

const runReadSchema = z.object({
  answer: z.object({ run: z.object({ id: z.uuid() }) }),
});

const findingReadsSchema = z
  .array(z.object({ answer: z.object({ finding: z.object({ id: z.int() }) }) }))
  .min(1);

const findingInputSchema = z.object({ run_id: z.uuid() });

function reportOf(runId: string): AuditReportLink {
  return { href: auditRunUrl(runId), label: REPORT };
}

function findingsLink(row: TraceRowView): AuditReportLink | null {
  const input = findingInputSchema.safeParse(row.input);
  const reads = findingReadsSchema.safeParse(row.output);
  if (!input.success || !reads.success) return null;
  const runId = input.data.run_id;
  const [only, ...rest] = reads.data;
  if (only === undefined || rest.length > 0) return reportOf(runId);
  return { href: auditFindingUrl(runId, only.answer.finding.id), label: FINDING };
}

export function auditReportLink(row: TraceRowView): AuditReportLink | null {
  if (!ANSWERED.has(row.status)) return null;
  switch (row.toolName) {
    case "start_gene_model_audit": {
      const started = startedSchema.safeParse(row.output);
      return started.success ? reportOf(started.data.answer.run_id) : null;
    }
    case "read_audit_run":
    case "review_audit_run": {
      const read = runReadSchema.safeParse(row.output);
      return read.success ? reportOf(read.data.answer.run.id) : null;
    }
    case "read_audit_findings":
      return findingsLink(row);
    default:
      return null;
  }
}
