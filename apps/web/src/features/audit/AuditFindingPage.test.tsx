/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { getAuditFindingSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useGetAuditFindingSuspense";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("origin=target"),
}));

import { auditWordsOptions } from "@/lib/api/audits";
import { createTestWrapper } from "@/lib/query/testing";

import {
  SAMPLE_DETAILS,
  SAMPLE_RUN,
  SAMPLE_RUN_ID,
  SAMPLE_WORDS,
  sampleDetail,
} from "./__fixtures__/sampleRun";
import { auditRunOptions } from "./api";
import { AuditFindingPage } from "./AuditFindingPage";

function renderFinding(detail: FindingDetail | undefined, id: string) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey, SAMPLE_RUN);
  queryClient.setQueryData(auditWordsOptions().queryKey, SAMPLE_WORDS);
  if (detail !== undefined) {
    queryClient.setQueryData(
      getAuditFindingSuspenseQueryOptions(SAMPLE_RUN_ID, Number(id)).queryKey,
      detail,
    );
  }
  render(<AuditFindingPage runId={SAMPLE_RUN_ID} findingId={id} />, {
    wrapper: Wrapper,
  });
}

describe("AuditFindingPage", () => {
  it("reads a finding: its outcome, verdict, genes, review and evidence", async () => {
    renderFinding(sampleDetail("strain_model"), "8");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Model too short" }),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("region", { name: "What the genome's DNA shows" }),
      ).getByText(
        "Related genomes match the reference, so the strain model is too short",
      ),
    ).toBeInTheDocument();
    const gene = screen.getByRole("link", { name: "Open PcyM_0736700 in PlasmoDB" });
    expect(gene).toHaveAttribute(
      "href",
      "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PcyM_0736700",
    );
    expect(gene).toHaveAttribute("target", "_blank");
    expect(gene).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByRole("region", { name: "Review" })).toHaveTextContent(
      "The review keeps the error",
    );
    expect(
      within(
        screen.getByRole("region", { name: "What the site's gene records hold" }),
      ).getByText("The site did not answer"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the audit" })).toHaveAttribute(
      "href",
      `/audits/${SAMPLE_RUN_ID}?origin=target`,
    );
  });

  it("names a finding the deadline left unread and shows no evidence for it", async () => {
    renderFinding(SAMPLE_DETAILS[4], "5");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Not checked: not read before the run's deadline",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No evidence was read for this finding."),
    ).toBeInTheDocument();
  });

  it("says a finding the check could not judge was not judged", async () => {
    const detail = sampleDetail("strain_model");
    renderFinding(
      {
        ...detail,
        finding: {
          ...detail.finding,
          errorType: null,
          errorTitle: null,
          judged: false,
        },
      },
      "8",
    );
    expect(
      await screen.findByText("The check could not judge this candidate."),
    ).toBeInTheDocument();
  });

  it("asks for nothing when the address names no finding", async () => {
    renderFinding(undefined, "not-a-number");
    expect(await screen.findByText("This finding does not exist.")).toBeInTheDocument();
  });
});
