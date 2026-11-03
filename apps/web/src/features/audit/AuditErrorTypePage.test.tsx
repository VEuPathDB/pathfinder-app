/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { listAuditFindingsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditFindingsSuspense";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(""),
}));

import { auditWordsOptions } from "@/lib/api/audits";
import { createTestWrapper } from "@/lib/query/testing";

import {
  SAMPLE_FINDINGS,
  SAMPLE_RUN,
  SAMPLE_RUN_ID,
  SAMPLE_WORDS,
} from "./__fixtures__/sampleRun";
import { auditRunOptions } from "./api";
import { AuditErrorTypePage } from "./AuditErrorTypePage";
import { filtersFromSearch, findingQuery } from "./findingQuery";

function renderErrorType(type: string) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey, SAMPLE_RUN);
  queryClient.setQueryData(auditWordsOptions().queryKey, SAMPLE_WORDS);
  const findings = SAMPLE_FINDINGS.findings.filter((f) => f.errorType === type);
  const state = {
    ...filtersFromSearch(new URLSearchParams()),
    errorType: findings[0]?.errorType ?? null,
  };
  queryClient.setQueryData(
    listAuditFindingsSuspenseQueryOptions(SAMPLE_RUN_ID, findingQuery(state)).queryKey,
    { ...SAMPLE_FINDINGS, total: findings.length, findings },
  );
  render(<AuditErrorTypePage runId={SAMPLE_RUN_ID} errorType={type} />, {
    wrapper: Wrapper,
  });
}

describe("AuditErrorTypePage", () => {
  it("reads one error type: what it is, why, how it was confirmed, and every gene", async () => {
    renderErrorType("missing_exon");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Exon missing from the model",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("RNA-seq reads join an exon the model does not have."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Sample review: RNA-seq junctions of 1,436 and 1,686 reads/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Findings, by the screen's impact: 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Two independent reviews agreed on 1 of 2 sampled findings (50%)",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the audit" })).toHaveAttribute(
      "href",
      `/audits/${SAMPLE_RUN_ID}`,
    );
  });

  it("keeps a filter change on this error type's address", async () => {
    replace.mockClear();
    renderErrorType("missing_exon");
    await userEvent.selectOptions(await screen.findByLabelText("Certainty"), "high");
    expect(screen.queryByLabelText("Error")).toBe(null);
    expect(replace).toHaveBeenCalledWith(
      `/audits/${SAMPLE_RUN_ID}/errors/missing_exon?certainty=high`,
      { scroll: false },
    );
  });

  it("says the audit names no such error and asks for no findings", async () => {
    renderErrorType("not_an_error");
    expect(
      await screen.findByText("This audit names no such error."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBe(null);
  });

  it("says the same for a real error type this run does not name", async () => {
    renderErrorType("fused_model");
    expect(
      await screen.findByText("This audit names no such error."),
    ).toBeInTheDocument();
  });

  it("says how a reviewed error type was confirmed from its own checks", async () => {
    const { queryClient, Wrapper } = createTestWrapper();
    const errorTypes = SAMPLE_RUN.errorTypes.map((type) => ({
      ...type,
      confirmedBy: null,
      cause: null,
      checks: ["gene_fusion" as const],
    }));
    queryClient.setQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey, {
      ...SAMPLE_RUN,
      errorTypes,
    });
    queryClient.setQueryData(auditWordsOptions().queryKey, SAMPLE_WORDS);
    queryClient.setQueryData(
      listAuditFindingsSuspenseQueryOptions(
        SAMPLE_RUN_ID,
        findingQuery({
          ...filtersFromSearch(new URLSearchParams()),
          errorType: "missing_exon",
        }),
      ).queryKey,
      { ...SAMPLE_FINDINGS, total: 0, findings: [] },
    );
    render(<AuditErrorTypePage runId={SAMPLE_RUN_ID} errorType="missing_exon" />, {
      wrapper: Wrapper,
    });
    expect(
      await screen.findByText(
        "Neighbouring genes fused into one model. Not summarized yet.",
      ),
    ).toBeInTheDocument();
  });
});
