import type { TraceRowStatus } from "@veupathdb/assistant-client";
import { describe, expect, it } from "vitest";

import { detail, RUN, SAMPLE_RUN } from "../__fixtures__/auditReads";
import { auditReportLink } from "./auditReportLink";
import type { TraceRowView } from "./traceTypes";

function row(
  toolName: string,
  output: unknown,
  status: TraceRowStatus = "ok",
  input: unknown = {},
): TraceRowView {
  return {
    key: "call_1",
    toolCallId: "call_1",
    toolName,
    summary: null,
    status,
    input,
    output,
    errorText: null,
  };
}

describe("auditReportLink", () => {
  it("links a start, a run read and one finding read", () => {
    expect(
      auditReportLink(row("start_gene_model_audit", { answer: { run_id: RUN } })),
    ).toEqual({ href: `/audits/${RUN}`, label: "Open the audit report" });
    expect(auditReportLink(row("read_audit_run", { answer: SAMPLE_RUN }))).toEqual({
      href: `/audits/${RUN}`,
      label: "Open the audit report",
    });
    expect(auditReportLink(row("review_audit_run", { answer: SAMPLE_RUN }))?.href).toBe(
      `/audits/${RUN}`,
    );
    expect(
      auditReportLink(
        row("read_audit_findings", [{ answer: detail(8) }], "ok", { run_id: RUN }),
      ),
    ).toEqual({ href: `/audits/${RUN}/findings/8`, label: "Open the finding" });
    expect(
      auditReportLink(
        row(
          "read_audit_findings",
          [{ answer: detail(8) }, { answer: detail(9) }],
          "ok",
          {
            run_id: RUN,
          },
        ),
      ),
    ).toEqual({ href: `/audits/${RUN}`, label: "Open the audit report" });
  });

  it("links a call that answered with a warning or an empty line", () => {
    expect(
      auditReportLink(row("read_audit_run", { answer: SAMPLE_RUN }, "warn"))?.href,
    ).toBe(`/audits/${RUN}`);
    expect(
      auditReportLink(row("read_audit_run", { answer: SAMPLE_RUN }, "empty"))?.href,
    ).toBe(`/audits/${RUN}`);
  });

  it("links nothing it cannot read", () => {
    expect(auditReportLink(row("read_audit_run", SAMPLE_RUN))).toBe(null);
    expect(auditReportLink(row("start_gene_model_audit", null, "error"))).toBe(null);
    expect(
      auditReportLink(
        row("start_gene_model_audit", { answer: { run_id: RUN } }, "running"),
      ),
    ).toBe(null);
    expect(
      auditReportLink(row("start_gene_model_audit", { answer: { run_id: "run" } })),
    ).toBe(null);
    expect(auditReportLink(row("list_audit_runs", []))).toBe(null);
    expect(auditReportLink(row("read_audit_findings", [], "ok", { run_id: RUN }))).toBe(
      null,
    );
    expect(auditReportLink(row("read_audit_findings", [{ answer: detail(8) }]))).toBe(
      null,
    );
  });
});
