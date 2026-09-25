"use client";

import type { ReactElement } from "react";
import type {
  Citation,
  RequirementCheck,
  SampledGene,
  VerificationReview,
} from "@pathfinder/shared";

import {
  ExhibitTable,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { useSiteLinkTarget } from "@/lib/hooks/useSiteLinkTarget";

import { referenceHref } from "./evidenceCards";

const REQUIREMENT_COLUMNS = [
  { head: "Requirement" },
  { head: "Answered by" },
  { head: "How" },
  { head: "Status" },
] as const;

const GENE_COLUMNS = [
  { head: "Gene" },
  { head: "Product" },
  { head: "Fits" },
  { head: "Why" },
] as const;

const STATUS_WORDS: Record<RequirementCheck["status"], string> = {
  met: "Met",
  unmet: "Not met",
  unexpressed: "No search states it",
};

const STATUS_TONE: Record<RequirementCheck["status"], string> = {
  met: "",
  unmet: "text-destructive",
  unexpressed: "text-warning",
};

const HOW_WORDS: Record<RequirementCheck["how"], string> = {
  search: "by a search",
  parameter: "by a parameter",
  structure: "by the structure",
  transform: "by a transform",
  analysis: "by an analysis",
};

const FIT_WORDS: Record<SampledGene["fits"], string> = {
  yes: "Fits",
  no: "Does not fit",
  unclear: "Unclear",
};

const COUNT_WORDS: Record<SampledGene["fits"], [one: string, many: string]> = {
  yes: ["fits", "fit"],
  no: ["does not fit", "do not fit"],
  unclear: ["unclear", "unclear"],
};

/** How many sampled genes carry each fit word, as the card and its caption say it. */
export function sampleCountLine(genes: readonly SampledGene[]): string {
  const count = (fit: SampledGene["fits"]) =>
    genes.filter((gene) => gene.fits === fit).length;
  const [only, ...others] = new Set(genes.map((gene) => gene.fits));
  if (only !== undefined && others.length === 0) {
    const [one, many] = COUNT_WORDS[only];
    const noun = genes.length === 1 ? "gene" : "genes";
    return `${genes.length} of ${genes.length} sampled ${noun} ${genes.length === 1 ? one : many}`;
  }
  const clauses = (["yes", "no", "unclear"] as const)
    .filter((fit) => fit === "yes" || count(fit) > 0)
    .map((fit) => `${count(fit)} ${COUNT_WORDS[fit][count(fit) === 1 ? 0 : 1]}`);
  return clauses.join(", ");
}

/** How many stated requirements the strategy meets. */
export function requirementCountLine(rows: readonly RequirementCheck[]): string {
  const met = rows.filter((row) => row.status === "met").length;
  return `${met} of ${rows.length} ${rows.length === 1 ? "requirement" : "requirements"} met`;
}

function requirementRow(row: RequirementCheck, index: number): ExhibitRow {
  const answeredBy = row.answeredBy ?? [];
  return {
    key: `${index}-${row.text}`,
    cells: [
      <div key="text">
        <p>{row.text}</p>
        <p className="text-[11px] text-muted-foreground">
          {`Message ${row.turn}${row.note == null || row.note === "" ? "" : `. ${row.note}`}`}
        </p>
      </div>,
      answeredBy.length > 0 ? (
        <span key="by" className="font-mono break-all">
          {answeredBy.join(", ")}
        </span>
      ) : (
        "-"
      ),
      HOW_WORDS[row.how],
      <span
        key="status"
        data-testid="evidence-requirement-status"
        className={STATUS_TONE[row.status]}
      >
        {STATUS_WORDS[row.status]}
      </span>,
    ],
  };
}

function geneRow(gene: SampledGene): ExhibitRow {
  return {
    key: gene.geneId,
    cells: [
      <span key="id" className="font-mono">
        {gene.geneId}
      </span>,
      gene.product ?? "",
      <span
        key="fits"
        data-testid="evidence-gene-fit"
        className={gene.fits === "no" ? "text-destructive" : ""}
      >
        {FIT_WORDS[gene.fits]}
      </span>,
      gene.why,
    ],
  };
}

function Sources({ cited }: { cited: readonly Citation[] }): ReactElement | null {
  const target = useSiteLinkTarget();
  if (cited.length === 0) return null;
  return (
    <div data-testid="evidence-sources" className="space-y-1 text-[11px]">
      <p className="text-muted-foreground">Sources the check read</p>
      <ul className="space-y-0.5">
        {cited.map((source) => {
          const reference = source.url ?? source.doi ?? source.pmid ?? "";
          const href = referenceHref(reference);
          return (
            <li key={reference}>
              {href === null ? (
                source.label
              ) : (
                <a
                  href={href}
                  target={target}
                  rel="noopener noreferrer"
                  className="text-primary underline-offset-2 hover:underline"
                >
                  {source.label}
                </a>
              )}
              <span className="text-muted-foreground">{`: ${source.why}`}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** What the check read against the researcher's words: each requirement, a
 * sample of the genes, and the sources it chose to read. */
export function EvidenceReview({
  review,
}: {
  review: VerificationReview | undefined;
}): ReactElement | null {
  const rows = review?.requirements ?? [];
  const genes = review?.sampledGenes ?? [];
  const sources = review?.sources ?? [];
  if (rows.length === 0 && genes.length === 0 && sources.length === 0) return null;
  return (
    <div data-testid="evidence-review" className="space-y-3">
      {rows.length > 0 ? (
        <div data-testid="evidence-requirements">
          <p className="mb-1.5 text-[11px] text-muted-foreground">
            {requirementCountLine(rows)}
          </p>
          <ExhibitTable columns={REQUIREMENT_COLUMNS} rows={rows.map(requirementRow)} />
        </div>
      ) : null}
      {genes.length > 0 ? (
        <div data-testid="evidence-sampled-genes">
          <p
            data-testid="evidence-sample-count"
            className="mb-1.5 text-[11px] text-muted-foreground"
          >
            {sampleCountLine(genes)}
          </p>
          <ExhibitTable columns={GENE_COLUMNS} rows={genes.map(geneRow)} />
        </div>
      ) : null}
      <Sources cited={sources} />
    </div>
  );
}
