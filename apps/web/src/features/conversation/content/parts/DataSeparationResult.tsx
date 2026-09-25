"use client";

import type { ReactElement } from "react";
import {
  COMBINE_OP_LABELS,
  type ControlSetEvidence,
  type SeparationOffer,
  type SeparationReport,
} from "@pathfinder/shared";
import type { StructureNode } from "@pathfinder/shared/generated/types/StructureNode";
import type { SkippedCriterionReasonEnumKey } from "@pathfinder/shared/generated/types/SkippedCriterion";

import { ExhibitTable } from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

const MEASURED_SHOWN = 10;

type Criterion = NonNullable<SeparationOffer["spec"]["criteria"]>[number];

function Cell({
  name,
  label,
  set,
  returned,
}: {
  name: string;
  label: string;
  set: ControlSetEvidence;
  returned: boolean;
}): ReactElement {
  const ids = returned ? set.returned : set.notReturned;
  return (
    <div
      data-testid={`separation-cell-${name}`}
      className="min-w-0 rounded-md border border-border bg-background/60 p-2"
    >
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p data-testid="separation-count" className="font-mono text-base font-medium">
        {ids.length}
      </p>
      <p
        data-testid="separation-ids"
        className="mt-1 max-h-20 overflow-y-auto break-words font-mono text-[10px] leading-relaxed text-muted-foreground"
      >
        {ids.join(", ")}
      </p>
    </div>
  );
}

function Matrix({ offer }: { offer: SeparationOffer }): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-2" aria-label="Controls the site returned">
      <Cell name="recovered" label="Positives returned" set={offer.positive} returned />
      <Cell
        name="missed"
        label="Positives missed"
        set={offer.positive}
        returned={false}
      />
      <Cell name="admitted" label="Negatives admitted" set={offer.negative} returned />
      <Cell
        name="excluded"
        label="Negatives excluded"
        set={offer.negative}
        returned={false}
      />
    </div>
  );
}

function TreeNode({
  node,
  titles,
}: {
  node: StructureNode;
  titles: Map<string, string>;
}): ReactElement {
  if (node.kind !== "combine" || node.operator == null) {
    return <li>{titles.get(node.criterionId ?? "") ?? node.criterionId}</li>;
  }
  return (
    <li>
      <span className="font-medium">{COMBINE_OP_LABELS[node.operator]}</span>
      <ul className="ml-3 list-disc pl-3">
        {(node.inputs ?? []).map((child, index) => (
          <TreeNode key={index} node={child} titles={titles} />
        ))}
      </ul>
    </li>
  );
}

function measuredShort(criterion: Criterion): string {
  const rationale = criterion.rationale;
  return rationale?.kind === "controls" ? rationale.short : "";
}

function Criteria({ offer }: { offer: SeparationOffer }): ReactElement {
  const lines = new Map(offer.contributions.map((c) => [c.criterionId, c.line]));
  return (
    <ExhibitTable
      testId="separation-criteria"
      columns={[{ head: "Search" }, { head: "Its own step" }, { head: "Ablation" }]}
      rows={(offer.spec.criteria ?? []).map((criterion) => ({
        key: criterion.id,
        cells: [
          criterion.text,
          measuredShort(criterion),
          lines.get(criterion.id) ?? "",
        ],
      }))}
    />
  );
}

function Measured({ report }: { report: SeparationReport }): ReactElement {
  const hidden = report.measured.length - MEASURED_SHOWN;
  return (
    <>
      <ExhibitTable
        testId="separation-measured"
        columns={[
          { head: "Measured search" },
          { head: "Drawn from" },
          { head: "Positives", numeric: true },
          { head: "Negatives", numeric: true },
          { head: "Genes", numeric: true },
        ]}
        rows={report.measured.slice(0, MEASURED_SHOWN).map((m) => ({
          key: m.candidateId,
          cells: [
            m.displayName,
            `${m.source}: ${m.basis}`,
            `${m.recovered} of ${m.positives}`,
            `${m.admitted} of ${m.negatives}`,
            m.resultSize.toLocaleString("en-US"),
          ],
        }))}
      />
      {hidden > 0 && (
        <p
          data-testid="separation-measured-more"
          className="text-[11px] text-muted-foreground"
        >
          {hidden} more measured searches are not shown.
        </p>
      )}
    </>
  );
}

function Unresolved({ report }: { report: SeparationReport }): ReactElement {
  const lists = [
    { kind: "positives", ids: report.unresolvedPositive ?? [] },
    { kind: "negatives", ids: report.unresolvedNegative ?? [] },
  ].filter((list) => list.ids.length > 0);
  return (
    <>
      {lists.map(({ kind, ids }) => (
        <p
          key={kind}
          data-testid="separation-unresolved"
          className="break-words text-[11px] text-foreground"
        >
          {ids.length} {kind} the site does not know: {ids.join(", ")}
        </p>
      ))}
    </>
  );
}

/** Why the run left a search unmeasured, in the researcher's words. */
const SKIP_WORDS: Record<SkippedCriterionReasonEnumKey, string> = {
  not_a_gene_search: "not a gene search",
  transform: "reads another step's result",
  needs_an_analysis: "needs a study analysis",
  takes_a_gene_list: "takes a list of gene IDs",
  unbound_required: "needs a value only you can set",
  vocabulary_miss: "no value matched",
  wdk_refused: "refused by the site",
  budget: "over the request budget",
  duplicate: "the same search as another",
  source_skipped: "its source was not measured",
};

function isSkipReason(reason: string): reason is SkippedCriterionReasonEnumKey {
  return Object.hasOwn(SKIP_WORDS, reason);
}

function skippedRows(report: SeparationReport): string[] {
  const reasons = Object.entries(report.skippedByReason ?? {}).map(
    ([reason, count]) =>
      `${isSkipReason(reason) ? SKIP_WORDS[reason] : reason}: ${count}`,
  );
  const neither = report.measured.filter((m) => m.informs === "neither").length;
  return neither === 0 ? reasons : [...reasons, `informs neither: ${neither}`];
}

function OfferBody({
  report,
  offer,
}: {
  report: SeparationReport;
  offer: SeparationOffer;
}): ReactElement {
  const titles = new Map((offer.spec.criteria ?? []).map((c) => [c.id, c.text]));
  const root = offer.spec.structure?.root;
  return (
    <div className="space-y-3">
      <Matrix offer={offer} />
      {root != null && (
        <ul data-testid="separation-tree" className="list-disc pl-4 text-[11px]">
          <TreeNode node={root} titles={titles} />
        </ul>
      )}
      <Criteria offer={offer} />
      {!offer.predictedMatchesRead && (
        <p data-testid="separation-predicted" className="text-[11px] text-foreground">
          The site&apos;s read of the tree differs from what the measured searches
          predicted.
        </p>
      )}
      <p className="text-[11px] text-muted-foreground">
        p = {offer.enrichment.pValue.toExponential(2)} that chance returns this many
        positives among the returned controls
      </p>
      <p
        data-testid="separation-informative"
        className="text-[11px] text-muted-foreground"
      >
        {report.informativeCount} of {report.measured.length} measured searches tell the
        positives from the negatives
      </p>
    </div>
  );
}

/** What one separation run measured, the strategy it offers, and its cost. */
export function DataSeparationResult({
  data,
}: {
  data: SeparationReport;
}): ReactElement {
  const offer = data.offer;
  return (
    <Figure testId="data-separation-result" title="Separation" caption={data.summary}>
      <div className="space-y-3">
        {offer != null && <OfferBody report={data} offer={offer} />}
        <Unresolved report={data} />
        {(data.shortfall ?? []).map((sentence) => (
          <p
            key={sentence}
            data-testid="separation-shortfall"
            className="text-[11px] text-foreground"
          >
            {sentence}
          </p>
        ))}
        <Measured report={data} />
        <ul className="text-[11px] text-muted-foreground">
          {skippedRows(data).map((row) => (
            <li key={row} data-testid="separation-skipped">
              {row}
            </li>
          ))}
        </ul>
        <p
          data-testid="separation-requests"
          className="text-[11px] text-muted-foreground"
        >
          {data.chargedRequests} of {data.budget} requests
        </p>
      </div>
    </Figure>
  );
}
