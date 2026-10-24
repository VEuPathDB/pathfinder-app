/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { AuditRunSummary } from "@pathfinder/shared/generated/types/AuditRunSummary";
import { listAuditRunsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditRunsSuspense";

import { auditWordsOptions } from "@/lib/api/audits";
import { createTestWrapper } from "@/lib/query/testing";

import served from "../../../../../packages/spec/audit_words.json";
import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { AuditRunsPage } from "./AuditRunsPage";

const HALTED: AuditRunSummary = {
  ...SAMPLE_RUN.run,
  id: "00000000-0000-4000-8000-000000000009",
  siteId: "toxodb",
  phase: "halted",
  genomes: ["Toxoplasma gondii ME49"],
  checks: ["gene_split", "selenoprotein_end"],
  targets: 0,
  createdAt: "2026-10-23T09:00:00Z",
};

function renderWith(runs: AuditRunSummary[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(listAuditRunsSuspenseQueryOptions().queryKey, runs);
  queryClient.setQueryData(auditWordsOptions().queryKey, served);
  return render(<AuditRunsPage />, { wrapper: Wrapper });
}

describe("AuditRunsPage", () => {
  it("lists each audit with its site, scope, checks and status, linked to its page", () => {
    renderWith([SAMPLE_RUN.run]);
    const link = screen.getByRole("link", {
      name: "Open the audit of Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets, started Oct 22, 2026",
    });
    expect(link).toHaveAttribute("href", `/audits/${SAMPLE_RUN_ID}`);
    expect(link).toHaveTextContent("Oct 22, 2026");
    const row = screen.getByRole("row", { name: /Plasmodium falciparum Dd2/ });
    expect(
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual([
      "Oct 22, 2026",
      "PlasmoDB",
      "Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets",
      "Gene length against orthologs; Exon structure against RNA-seq; Organelle genes at the circular join; Pseudogene calls on intact genes; Strain model against its reference",
      "Finished",
    ]);
    expect(
      screen.getByRole("table", { name: "Your audits, newest first" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("columnheader").map((header) => header.textContent),
    ).toEqual(["Started", "Site", "What it examines", "Checks", "Status"]);
  });

  it("keeps the order the API lists the audits in", () => {
    renderWith([HALTED, SAMPLE_RUN.run]);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      [
        "Oct 23, 2026",
        "ToxoDB",
        "Toxoplasma gondii ME49",
        "One gene split into two models; Selenoproteins cut at their selenocysteine",
        "Stopped",
      ],
      [
        "Oct 22, 2026",
        "PlasmoDB",
        "Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets",
        "Gene length against orthologs; Exon structure against RNA-seq; Organelle genes at the circular join; Pseudogene calls on intact genes; Strain model against its reference",
        "Finished",
      ],
    ]);
    expect(
      screen.getByRole("link", {
        name: "Open the audit of Toxoplasma gondii ME49, started Oct 23, 2026",
      }),
    ).toHaveAttribute("href", "/audits/00000000-0000-4000-8000-000000000009");
  });

  it("says how to start one when there is none", () => {
    renderWith([]);
    expect(
      screen.getByText(
        "No audits yet. Ask the audit assistant in a conversation to audit a genome.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
