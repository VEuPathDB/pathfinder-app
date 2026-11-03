/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { listAuditFindingsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditFindingsSuspense";
import type { FindingPage } from "@pathfinder/shared/generated/types/FindingPage";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams("origin=target"),
}));
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
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
import { AuditRunPage } from "./AuditRunPage";
import { filtersFromSearch, findingQuery } from "./findingQuery";

function renderPage(findings: FindingPage) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey, SAMPLE_RUN);
  queryClient.setQueryData(auditWordsOptions().queryKey, SAMPLE_WORDS);
  const state = filtersFromSearch(new URLSearchParams("origin=target"));
  queryClient.setQueryData(
    listAuditFindingsSuspenseQueryOptions(SAMPLE_RUN_ID, findingQuery(state)).queryKey,
    findings,
  );
  render(<AuditRunPage runId={SAMPLE_RUN_ID} />, { wrapper: Wrapper });
}

describe("AuditRunPage", () => {
  it("reads one run top to bottom, with the findings the address filters", async () => {
    const targets = SAMPLE_FINDINGS.findings.filter((finding) => finding.fromTarget);
    renderPage({ ...SAMPLE_FINDINGS, total: targets.length, findings: targets });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Audit of",
    );
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual([
      "Progress",
      "Headline findings",
      "Error rates",
      "Your gene targets",
      "Findings",
    ]);
    expect(screen.getByLabelText("Source")).toHaveValue("target");
    expect(
      screen.getByRole("table", { name: "Findings, highest impact first: 3" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Download the 10 findings of this audit as a spreadsheet (CSV)",
      }),
    ).toHaveAttribute("download");
    await userEvent.selectOptions(screen.getByLabelText("Certainty"), "high");
    expect(replace).toHaveBeenCalledWith(
      `/audits/${SAMPLE_RUN_ID}?certainty=high&origin=target`,
      { scroll: false },
    );
    expect(screen.getByRole("link", { name: "All audits" })).toHaveAttribute(
      "href",
      "/audits",
    );
    expect(
      screen.getByRole("button", { name: "Retry what was not read" }),
    ).toBeEnabled();
  });
});
