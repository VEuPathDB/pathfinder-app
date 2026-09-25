"use client";

import type { ReactElement } from "react";
import {
  siteShortName,
  type CheckedStepCount,
  type ControlSetEvidence,
  type ControlTestEvidence,
  type CriterionCitations,
  type EvidenceCard,
} from "@pathfinder/shared";

import { CountOfIds } from "@/features/conversation/thread/CountOfIds";
import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { useSiteLinkTarget } from "@/lib/hooks/useSiteLinkTarget";

import { referenceHref } from "./evidenceCards";
import { EvidenceReview } from "./EvidenceReview";

type ControlKind = "positive" | "negative";

const RATE_DIGITS = 2;
const P_DIGITS = 2;

const CONTROL_COLUMNS = [
  { head: "Control set" },
  { head: "Controls", numeric: true },
  { head: "Returned", numeric: true },
  { head: "Not returned", numeric: true },
  { head: "Rate", numeric: true },
] as const;

const STEP_COLUMNS = [
  { head: "Step" },
  { head: "Recorded at the build", numeric: true },
  { head: "On the site at the check", numeric: true },
] as const;

/** The words each kind uses for its two lists. */
const LIST_WORDS: Record<ControlKind, { returned: string; notReturned: string }> = {
  positive: { returned: "recovered", notReturned: "missed" },
  negative: { returned: "returned", notReturned: "excluded" },
};

function verdictLine(card: EvidenceCard): string {
  const { verdict } = card;
  if (!verdict.supported) {
    return verdict.refusedBecause == null
      ? "Not supported"
      : `Not supported: ${verdict.refusedBecause}`;
  }
  const pending = verdict.pendingChecks ?? [];
  if (pending.length === 0) return "Supported";
  return `Supported, ${pending.length} ${pending.length === 1 ? "check" : "checks"} pending: ${pending.join(", ")}`;
}

function controlRow(set: ControlSetEvidence, kind: ControlKind): ExhibitRow {
  const words = LIST_WORDS[kind];
  const noun = `${kind} controls`;
  return {
    key: kind,
    cells: [
      kind === "positive" ? "Positive" : "Negative",
      <CountOfIds
        key="controls"
        count={set.controlsCount}
        ids={[...set.returned, ...set.notReturned]}
        noun={noun}
      />,
      <CountOfIds
        key="returned"
        count={set.returnedCount}
        ids={set.returned}
        noun={`${noun} ${words.returned}`}
      />,
      <CountOfIds
        key="not-returned"
        count={set.notReturned.length}
        ids={set.notReturned}
        noun={`${noun} ${words.notReturned}`}
      />,
      set.rate.toFixed(RATE_DIGITS),
    ],
  };
}

function idNote(key: string, label: string, ids: readonly string[]): ExhibitNote[] {
  if (ids.length === 0) return [];
  return [
    {
      key,
      label,
      body: (
        <span data-testid={`evidence-ids-${key}`} className="font-mono break-all">
          {ids.join(", ")}
        </span>
      ),
    },
  ];
}

function setNotes(
  set: ControlSetEvidence | null | undefined,
  kind: ControlKind,
): ExhibitNote[] {
  if (set == null) return [];
  const words = LIST_WORDS[kind];
  const name = kind === "positive" ? "Positives" : "Negatives";
  return [
    ...idNote(`${kind}-returned`, `${name} ${words.returned}:`, set.returned),
    ...idNote(`${kind}-not-returned`, `${name} ${words.notReturned}:`, set.notReturned),
  ];
}

function enrichmentNote(test: ControlTestEvidence): ExhibitNote[] {
  const found = test.enrichment;
  if (found == null) return [];
  return [
    {
      key: "enrichment",
      label: "Positives among the returned controls:",
      body: `${found.positivesReturned} of ${found.returned} returned, ${found.positives} positives in ${found.population} controls, one-sided hypergeometric p = ${found.pValue.toPrecision(P_DIGITS)}`,
    },
  ];
}

function ControlTest({ test }: { test: ControlTestEvidence }): ReactElement {
  const rows: ExhibitRow[] = [];
  if (test.positive != null) rows.push(controlRow(test.positive, "positive"));
  if (test.negative != null) rows.push(controlRow(test.negative, "negative"));
  return (
    <div data-testid="evidence-controls">
      <p className="mb-1.5 text-[11px] text-muted-foreground">
        {`Control test on ${test.testedLabel}`}
      </p>
      <ExhibitTable
        columns={CONTROL_COLUMNS}
        rows={rows}
        notes={[
          ...setNotes(test.positive, "positive"),
          ...setNotes(test.negative, "negative"),
          ...enrichmentNote(test),
        ]}
      />
    </div>
  );
}

function stepRow(step: CheckedStepCount): ExhibitRow {
  const site = step.siteCount == null ? "-" : step.siteCount.toLocaleString();
  return {
    key: step.stepId,
    cells: [
      step.title,
      step.recordedCount == null ? "-" : step.recordedCount.toLocaleString(),
      step.drifted ? (
        <span data-testid="evidence-step-changed" className="text-warning">
          {`${site} (changed on the site)`}
        </span>
      ) : (
        site
      ),
    ],
  };
}

function Citations({
  cited,
}: {
  cited: readonly CriterionCitations[];
}): ReactElement | null {
  const target = useSiteLinkTarget();
  if (cited.length === 0) return null;
  return (
    <dl data-testid="evidence-citations" className="space-y-1 text-[11px]">
      {cited.map((criterion) => (
        <div key={criterion.criterionId}>
          <dt className="text-muted-foreground">{criterion.criterionText}</dt>
          {criterion.references.map((reference) => {
            const href = referenceHref(reference);
            return (
              <dd key={reference} className="break-all">
                {href === null ? (
                  reference
                ) : (
                  <a
                    href={href}
                    target={target}
                    rel="noopener noreferrer"
                    className="text-primary underline-offset-2 hover:underline"
                  >
                    {reference}
                  </a>
                )}
              </dd>
            );
          })}
        </div>
      ))}
    </dl>
  );
}

function SiteLinks({ url, siteId }: { url: string; siteId: string }): ReactElement {
  const target = useSiteLinkTarget();
  const site = siteShortName(siteId);
  const link = "text-primary underline-offset-2 hover:underline";
  return (
    <div className="flex flex-col gap-0.5 text-xs">
      <a
        data-testid="evidence-strategy-link"
        href={url}
        target={target}
        rel="noopener noreferrer"
        aria-label={`Open in ${site}`}
        className={link}
      >
        {`Open in ${site}`}
      </a>
      <a href={url} target={target} rel="noopener noreferrer" className={link}>
        {`Run GO, pathway or word enrichment in ${site}`}
      </a>
    </div>
  );
}

/** Every value of one check's evidence, as the thread and the rail both draw it. */
export function EvidenceCardBody({
  card,
  superseded = false,
}: {
  card: EvidenceCard;
  superseded?: boolean;
}): ReactElement {
  return (
    <div data-testid="evidence-card-body" className="min-w-0 space-y-3">
      <p data-testid="evidence-verdict" className="text-sm font-medium">
        {verdictLine(card)}
      </p>
      {superseded ? (
        <p data-testid="evidence-superseded" className="text-[11px] text-warning">
          Superseded: the strategy changed after this check.
        </p>
      ) : null}
      {card.controls.map((test) => (
        <ControlTest
          key={`${test.wdkStepId ?? "search"}-${test.testedLabel}`}
          test={test}
        />
      ))}
      {card.steps.length > 0 ? (
        <div data-testid="evidence-steps">
          <ExhibitTable columns={STEP_COLUMNS} rows={card.steps.map(stepRow)} />
          {card.siteRead !== "not_answered" ? null : (
            <p className="mt-1 text-[11px] text-muted-foreground">
              The site did not answer at the check, so no count is shown for it.
            </p>
          )}
        </div>
      ) : null}
      <EvidenceReview review={card.review} />
      <Citations cited={card.citations} />
      {card.strategyUrl == null ? null : (
        <SiteLinks url={card.strategyUrl} siteId={card.siteId} />
      )}
    </div>
  );
}
