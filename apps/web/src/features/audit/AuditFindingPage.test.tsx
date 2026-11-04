/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { getAuditFindingSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useGetAuditFindingSuspense";
import type { ConfirmationEvidence } from "@pathfinder/shared/generated/types/ConfirmationEvidence";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { RelativesEvidence } from "@pathfinder/shared/generated/types/RelativesEvidence";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("origin=target"),
}));

import { auditWordsOptions } from "@/lib/api/audits";
import { createTestWrapper } from "@/lib/query/testing";

import {
  NAC_MISSING_IN_GT1,
  RELATIVES_NO_REFERENCE_ROW,
} from "./__fixtures__/derivedAudits";
import { SELK_STOPS_AT_SEC } from "./__fixtures__/recordedAudits";
import { GT1_SELK_MODELS } from "./__fixtures__/recordedModels";
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

function stored(payload: EvidenceView["payload"], kind: EvidenceView["kind"]) {
  return {
    kind,
    status: "stored" as const,
    payload,
    requests: 0,
    attempts: 1,
    stopped: 0,
    message: null,
  };
}

function withConfirmation(
  detail: FindingDetail,
  confirmation: ConfirmationEvidence["confirmation"],
): FindingDetail {
  return {
    ...detail,
    evidence: [
      stored({ kind: "confirmation", confirmation }, "confirmation"),
      ...detail.evidence.filter((evidence) => evidence.kind !== "confirmation"),
    ],
  };
}

function withRelatives(relatives: RelativesEvidence): FindingDetail {
  const detail = sampleDetail("gene_length");
  return {
    ...detail,
    evidence: [
      ...detail.evidence,
      stored({ ...relatives, kind: "relatives" }, "relatives"),
    ],
  };
}

function regionNamed(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

const DNA = "What the genome's DNA shows";
const RECORDS = "What the site's gene records hold";
const RELATIVES = "Lengths in related genomes";
const NO_MODEL = "No gene model stored for this finding";

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

  it.each([
    [0, "1", ["High certainty", "Source: Random sample", "6 site requests"]],
    [7, "8", ["High certainty", "Source: Your gene target", "0 site requests"]],
    [1, "2", ["Source: Random sample", "0 site requests"]],
    [2, "3", ["Source: Random sample", "0 site requests"]],
    [4, "5", ["Source: Random sample"]],
    [5, "6", ["Source: Random sample"]],
    [6, "7", ["Source: Not in the random sample"]],
  ])(
    "states only what sample finding %i stores in its head",
    async (index, id, stated) => {
      const detail = SAMPLE_DETAILS[index];
      if (detail === undefined) throw new Error(`no sample finding ${id}`);
      renderFinding(detail, id);
      const head = await screen.findByRole("list", { name: "About this finding" });
      expect(
        within(head)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual(stated);
    },
  );

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

  it("draws a strain finding's models, proteins and relatives from what it stores", async () => {
    renderFinding(sampleDetail("strain_model"), "8");
    await screen.findByRole("heading", { level: 2, name: "Gene models" });
    expect(screen.queryByText(NO_MODEL)).toBe(null);
    const models = screen.getByRole("region", { name: "Gene models" });
    expect(
      within(models).getByRole("img", {
        name: /Gene models on PcyM_07, bases 1,381,622 to 1,383,462/,
      }),
    ).toBeInTheDocument();
    expect(
      within(models).getByRole("img", { name: /Gene models on DF157099/ }),
    ).toBeInTheDocument();
    const proteins = screen.getAllByRole("img", {
      name: /Protein lengths of the two models/,
    });
    expect(proteins).toHaveLength(1);
    expect(proteins[0]?.querySelectorAll('[data-kind="missing"]').length).toBe(1);
    const dna = regionNamed(DNA);
    const plot = within(dna).getByRole("img", {
      name: "Protein lengths: this model 280 residues, reference 341 residues, median 340 residues, Plasmodium relative0 X 335 residues, Plasmodium relative1 X 345 residues",
    });
    expect(plot.querySelectorAll('[data-part="relative"]')).toHaveLength(2);
    expect(within(dna).getByText("Median of the related genomes")).toBeInTheDocument();
  });

  it("draws an intron finding's annotated model against the proposed one", async () => {
    renderFinding(sampleDetail("intron_support"), "10");
    const figure = await screen.findByRole("img", {
      name: /Gene models on PcyM_07, bases 1,381,622 to 1,383,462/,
    });
    expect(figure.querySelectorAll("g[data-row]")).toHaveLength(2);
    expect(figure.querySelectorAll('[data-part="junction"]')).toHaveLength(2);
    expect(
      within(regionNamed(DNA)).getByText("Intron with no read").nextElementSibling,
    ).toHaveTextContent("bases 1,381,746 to 1,382,305");
  });

  it("carries a pseudogene's codons in its confirmation when no gene model is stored", async () => {
    renderFinding(sampleDetail("pseudogene_call"), "1");
    expect(await screen.findByText(NO_MODEL)).toBeInTheDocument();
    expect(
      within(regionNamed(DNA)).getByRole("img", {
        name: /Coding sequences of the two genes, in codons.*Reference PF3D7_1032400, translated codons: 462 codons/,
      }),
    ).toBeInTheDocument();
  });

  it("draws the transcripts a gene record holds beside the record's words", async () => {
    renderFinding(sampleDetail("pseudogene_call"), "1");
    const records = await screen.findByRole("region", { name: RECORDS });
    const figure = within(records).getByRole("img", {
      name: /Protein lengths of the transcripts of PF3D7_1032400/,
    });
    expect(figure.querySelectorAll('[data-kind="structure"]')).toHaveLength(1);
    expect(
      within(records).getByRole("table", {
        name: "PDB similarities of PF3D7_1032400: 4",
      }),
    ).toBeInTheDocument();
    expect(within(records).getByText("PF3D7_1032400 citations")).toBeInTheDocument();
  });

  it("states how the finding's impact was weighed", async () => {
    renderFinding(sampleDetail("pseudogene_call"), "1");
    const impact = await screen.findByRole("region", { name: "Impact 0.5" });
    expect(within(impact).getAllByRole("listitem")[0]).toHaveTextContent(
      "Certainty: 1 (high certainty)",
    );
    expect(within(impact).getAllByRole("listitem")[2]).toHaveTextContent(
      "Genome use: 0.5, because the site does not mark this genome as its species' reference strain (Plasmodium falciparum NF54)",
    );
  });

  it("says a finding with no error was not weighed", async () => {
    renderFinding(SAMPLE_DETAILS[2], "3");
    expect(
      within(await screen.findByRole("region", { name: "Impact" })).getByText(
        "Not weighed: only a finding that names an error has an impact.",
      ),
    ).toBeInTheDocument();
  });

  it("draws a selenoprotein's residues and its stored models", async () => {
    const detail = sampleDetail("organelle_join");
    renderFinding(
      {
        ...withConfirmation(detail, {
          check: "selenoprotein_end",
          result: SELK_STOPS_AT_SEC,
        }),
        models: GT1_SELK_MODELS,
      },
      "9",
    );
    expect(
      within(await screen.findByRole("region", { name: DNA })).getByRole("img", {
        name: /Genome after the model's end: stop, G, stop/,
      }),
    ).toBeInTheDocument();
    expect(
      screen
        .getByRole("region", { name: "Gene models" })
        .querySelectorAll("g[data-row]"),
    ).toHaveLength(2);
  });

  it("draws a missing gene's locus in its confirmation", async () => {
    const detail = sampleDetail("organelle_join");
    renderFinding(
      withConfirmation(detail, { check: "missing_gene", result: NAC_MISSING_IN_GT1 }),
      "9",
    );
    const locus = within(await screen.findByRole("region", { name: DNA })).getByRole(
      "img",
      { name: /The locus of TGARI_257090 in Toxoplasma gondii GT1/ },
    );
    expect(locus.querySelectorAll('[data-part="anchor"]')).toHaveLength(2);
  });

  it("draws no locus for a missing gene that read no anchors", async () => {
    renderFinding(
      withConfirmation(sampleDetail("organelle_join"), {
        check: "missing_gene",
        result: { ...NAC_MISSING_IN_GT1, anchors: null, located: null },
      }),
      "9",
    );
    expect(
      within(await screen.findByRole("region", { name: DNA })).queryByRole("img"),
    ).toBe(null);
  });

  it("draws the relatives a length finding stores in their own section", async () => {
    renderFinding(
      withRelatives({
        ...RELATIVES_NO_REFERENCE_ROW,
        referenceOrganism: "Plasmodium falciparum 3D7",
        modelLength: 110,
        referenceLength: 319,
        relativesMedian: 300,
        relativeLengths: { "Relative A": 319, "Relative B": 296 },
      }),
      "2",
    );
    const figure = within(
      await screen.findByRole("region", { name: RELATIVES }),
    ).getByRole("img", { name: /median 300 residues/ });
    expect(figure.querySelectorAll('[data-part="relative"]')).toHaveLength(2);
    expect(figure.querySelectorAll('[data-part="model"]')).toHaveLength(1);
  });

  it("says why stored relatives draw no plot", async () => {
    renderFinding(withRelatives(RELATIVES_NO_REFERENCE_ROW), "2");
    const region = await screen.findByRole("region", { name: RELATIVES });
    expect(
      within(region).getByText(
        "The gene records hold no row of the reference gene, so no related genome was compared.",
      ),
    ).toBeInTheDocument();
    expect(within(region).queryByRole("img")).toBe(null);
  });

  it("shows the note of a row that is not stored and draws nothing from it", async () => {
    const detail = sampleDetail("strain_model");
    renderFinding(
      {
        ...detail,
        models: null,
        evidence: detail.evidence.map((evidence) =>
          evidence.kind === "confirmation"
            ? { ...evidence, status: "failed", message: "the record is unreadable" }
            : evidence,
        ),
      },
      "8",
    );
    const dna = await screen.findByRole("region", { name: DNA });
    expect(
      within(dna).getByText("Could not be read: the record is unreadable"),
    ).toBeInTheDocument();
    expect(within(dna).queryByRole("img")).toBe(null);
    const records = regionNamed(RECORDS);
    expect(within(records).getByText("The site did not answer")).toBeInTheDocument();
    expect(within(records).queryByRole("img")).toBe(null);
    expect(screen.queryByRole("img")).toBe(null);
  });

  it("keeps the words and draws nothing for a stored row whose payload it cannot draw", async () => {
    const detail = sampleDetail("strain_model");
    renderFinding(
      {
        ...detail,
        models: null,
        evidence: [
          stored(null, "confirmation"),
          stored({ ...RELATIVES_NO_REFERENCE_ROW, kind: "relatives" }, "gene_evidence"),
        ],
        facts: [
          ...detail.facts,
          { kind: "gene_evidence", facts: [{ label: "Stated", value: "kept" }] },
        ],
      },
      "8",
    );
    const dna = await screen.findByRole("region", { name: DNA });
    expect(within(dna).queryByRole("img")).toBe(null);
    expect(
      within(dna).getByText("Reference residues the strain model lacks"),
    ).toBeInTheDocument();
    expect(within(regionNamed(RECORDS)).getByText("Stated")).toBeInTheDocument();
    expect(screen.getByText(NO_MODEL)).toBeInTheDocument();
  });

  it("says no gene model is stored when the stored models hold no span to draw", async () => {
    const detail = sampleDetail("strain_model");
    const models = detail.models;
    if (models === null) throw new Error("the sample strain finding stores its models");
    renderFinding({ ...detail, models: { ...models, annotated: [] } }, "8");
    expect(await screen.findByText(NO_MODEL)).toBeInTheDocument();
    expect(
      within(regionNamed(DNA)).getByRole("img", {
        name: /Protein lengths of the two models/,
      }),
    ).toBeInTheDocument();
  });
});
