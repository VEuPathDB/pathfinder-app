"use client";

import type { ReactElement } from "react";
import type {
  Citation,
  ColumnFit,
  SampledGene,
  SiteCheck,
  VerificationReview,
} from "@pathfinder/shared";

import {
  ExhibitTable,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";

import { referenceHref } from "./evidenceCards";

const CHECK_COLUMNS = [
  { head: "Check" },
  { head: "Result" },
  { head: "What the site answered" },
] as const;

const FIT_COLUMNS = [
  { head: "Search" },
  { head: "Column" },
  { head: "Bound" },
  { head: "Fit", numeric: true },
] as const;

const GENE_COLUMNS = [
  { head: "Gene" },
  { head: "Product" },
  { head: "Fits" },
  { head: "Why" },
] as const;

const STATUS_WORDS: Record<SiteCheck["status"], string> = {
  pass: "Passed",
  fail: "Failed",
  unchecked: "Not checked",
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

function checkRow(check: SiteCheck, index: number): ExhibitRow {
  return {
    key: `${index}-${check.kind}-${check.subject}`,
    testId: "evidence-check",
    cells: [
      check.subject,
      <span key="status" className={check.status === "fail" ? "text-destructive" : ""}>
        {STATUS_WORDS[check.status]}
      </span>,
      check.evidence,
    ],
  };
}

/** The records inside the bound out of the step, or that the site refused the column. */
/** A threshold the step holds on neither side is stated with the count on each
 * side, which the fit's own sentence carries. */
function fitCount(fit: ColumnFit): string {
  if (fit.fits === "not_shown")
    return `The site refused this column (HTTP ${fit.refusedStatus})`;
  if ((fit.sides ?? []).length > 0) return fit.sentence;
  const inside =
    fit.fitting === fit.fittingAtMost
      ? `${fit.fitting}`
      : `${fit.fitting} to ${fit.fittingAtMost}`;
  return `${inside} of ${fit.total} ${fit.countedIn}`;
}

/** Every record inside the known bounds; an open side is a count, not a misfit. */
function fitsEveryRecord(fit: ColumnFit): boolean {
  if (fit.fits === "all") return true;
  return (fit.sides ?? []).length > 0 && fit.fitting === fit.total;
}

function fitRow(fit: ColumnFit): ExhibitRow {
  return {
    key: `${fit.wdkStepId}-${fit.column}`,
    testId: "evidence-column-fit",
    cells: [
      fit.criterionText,
      <span key="column" className="font-mono">
        {fit.displayName}
      </span>,
      fit.boundValue,
      <span key="fit" className={fitsEveryRecord(fit) ? "" : "text-destructive"}>
        {fitCount(fit)}
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
                  target="_blank"
                  rel="noreferrer"
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

/** What the check read: each check the site's answers decide, the columns of
 * each step, a sample of the genes where no column shows, and the sources it
 * chose to read. */
export function EvidenceReview({
  review,
}: {
  review: VerificationReview | undefined;
}): ReactElement | null {
  const checks = review?.checks ?? [];
  const fits = review?.columnFits ?? [];
  const genes = review?.sampledGenes ?? [];
  const sources = review?.sources ?? [];
  const withheld = review?.withheld ?? [];
  if ([checks, fits, genes, sources, withheld].every((part) => part.length === 0)) {
    return null;
  }
  return (
    <div data-testid="evidence-review" className="space-y-3">
      {checks.length > 0 ? (
        <div data-testid="evidence-checks">
          <ExhibitTable columns={CHECK_COLUMNS} rows={checks.map(checkRow)} />
        </div>
      ) : null}
      {fits.length > 0 ? (
        <div data-testid="evidence-column-fits">
          <ExhibitTable columns={FIT_COLUMNS} rows={fits.map(fitRow)} />
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
      {withheld.length > 0 ? (
        <ul
          data-testid="evidence-withheld"
          className="space-y-1 text-[11px] text-muted-foreground"
        >
          {withheld.map((item) => (
            <li key={item.sentence} data-testid="evidence-withheld-item">
              {item.sentence}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
