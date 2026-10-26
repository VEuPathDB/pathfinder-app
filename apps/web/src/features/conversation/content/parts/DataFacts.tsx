"use client";

import type { ReactElement } from "react";
import { siteShortName } from "@pathfinder/shared";
import type { ParameterFact, StepFact, TurnFacts } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";
import {
  ListedTables,
  MoreValueTables,
  OrthologTables,
  RecordsTable,
} from "@/features/conversation/content/parts/FactsRecords";

import { FactsExpression } from "./FactsExpression";

const SOURCE_LABELS: Record<ParameterFact["source"], string> = {
  stated: "stated",
  chosen: "chosen",
  default: "site default",
  card: "your answer",
  held: "in the strategy",
};

function counted(count: number | null | undefined, noun: string): string {
  if (count === null || count === undefined) return "count not available";
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}

function withBefore(
  count: number | null | undefined,
  before: number | null | undefined,
  noun: string,
): string {
  if (before === null || before === undefined) return counted(count, noun);
  return `${counted(count, noun)}, ${counted(before, noun)} before this turn's edit`;
}

type LastChange = NonNullable<TurnFacts["lastChange"]>;

function changeSide(
  count: number | null | undefined,
  side: string,
  noun: string,
): string {
  if (count === null || count === undefined) return `count ${side} not recorded`;
  return `${counted(count, noun)} ${side}`;
}

function lastChangeLine(change: LastChange, noun: string): string {
  const before = changeSide(change.before, "before", noun);
  return `Last change: ${change.what}; ${before}, ${changeSide(change.after, "after", noun)}`;
}

function Parameter({ fact }: { fact: ParameterFact }): ReactElement {
  const label = fact.label ?? "";
  const expression = fact.expression ?? "";
  return (
    <li data-testid="facts-param" data-source={fact.source} className="text-xs">
      <span className="text-muted-foreground">{fact.displayName}: </span>
      {expression === "" ? (
        <span data-testid="facts-param-value">
          {fact.value}
          {label === "" ? null : ` (${label})`}
        </span>
      ) : null}
      <span className="ml-1 text-muted-foreground">({SOURCE_LABELS[fact.source]})</span>
      {expression === "" ? null : <FactsExpression expression={expression} />}
      {(fact.notes ?? []).map((note) => (
        <div
          key={note}
          data-testid="facts-param-note"
          className="text-muted-foreground"
        >
          {note}
        </div>
      ))}
    </li>
  );
}

function Step({ step }: { step: StepFact }): ReactElement {
  const error = step.error ?? "";
  return (
    <li data-testid="facts-step" data-step-name={step.displayName} className="py-1">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span data-testid="facts-step-name" className="font-medium">
          {step.operator == null ? null : (
            <span className="mr-1 text-xs text-muted-foreground">{step.operator}</span>
          )}
          {step.displayName}
        </span>
        <span data-testid="facts-step-count" data-count={step.count ?? ""}>
          {withBefore(step.count, step.countBefore, step.recordNoun ?? "gene")}
        </span>
      </div>
      {(step.reason ?? "") === "" ? null : (
        <div data-testid="facts-step-reason" className="text-xs text-muted-foreground">
          {step.reason}
        </div>
      )}
      {(step.alsoConsidered ?? []).length === 0 ? null : (
        <div
          data-testid="facts-step-considered"
          className="text-xs text-muted-foreground"
        >
          {`Also considered: ${(step.alsoConsidered ?? []).join(", ")}`}
        </div>
      )}
      {(step.parameters ?? []).length === 0 ? null : (
        <ul className="ml-3">
          {(step.parameters ?? []).map((fact) => (
            <Parameter key={fact.name} fact={fact} />
          ))}
        </ul>
      )}
      {error === "" ? null : (
        <div data-testid="facts-step-error" className="text-xs text-destructive">
          {error}
        </div>
      )}
    </li>
  );
}

function Sentences({
  testId,
  items,
}: {
  testId: string;
  items: { key: string; kind?: string; text: string }[];
}): ReactElement | null {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 text-xs">
      {items.map((item) => (
        <li key={item.key} data-testid={testId} data-kind={item.kind}>
          {item.text}
        </li>
      ))}
    </ul>
  );
}

/** What the turn holds, rendered in the turn's appendix: the steps with their
 * values and counts, what the check measured, and what the turn saved. The
 * reply restates none of it. */
export function DataFacts({ data }: { data: TurnFacts }): ReactElement {
  const noun = data.recordNoun ?? "gene";
  const steps = data.steps ?? [];
  const link = data.strategyLink ?? null;
  const sources = data.sources ?? [];
  const named = data.namedGenes ?? [];
  return (
    <Figure
      testId="data-facts"
      title={data.draft === true ? "Plan" : "Strategy"}
      caption={null}
    >
      {steps.length === 0 ? null : (
        <ul className="divide-y">
          {steps.map((step) => (
            <Step key={step.stepId} step={step} />
          ))}
        </ul>
      )}
      {data.rootCount == null ? null : (
        <div
          data-testid="facts-root-count"
          data-count={data.rootCount}
          className="mt-1 text-sm font-medium"
        >
          Result: {withBefore(data.rootCount, data.rootCountBefore, noun)}
        </div>
      )}
      {data.lastChange == null ? null : (
        <div data-testid="facts-last-change" className="mt-1 text-sm">
          {lastChangeLine(data.lastChange, noun)}
        </div>
      )}
      <Sentences
        testId="facts-removed"
        items={(data.removed ?? []).map((title) => ({
          key: title,
          text: `Removed ${title}`,
        }))}
      />
      {link === null ? null : (
        <a
          data-testid="facts-strategy-link"
          href={link.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 block text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          {`Open on ${siteShortName(link.siteId)}`}
        </a>
      )}
      <Sentences
        testId="facts-caveat"
        items={(data.caveats ?? []).map((caveat) => ({
          key: `${caveat.kind}:${caveat.sentence}`,
          kind: caveat.kind,
          text: caveat.sentence,
        }))}
      />
      <Sentences
        testId="facts-gap"
        items={(data.gaps ?? []).map((gap) => ({
          key: `${gap.kind}:${gap.sentence}`,
          kind: gap.kind,
          text: gap.sentence,
        }))}
      />
      <Sentences
        testId="facts-column-fit"
        items={(data.columnFits ?? []).map((fit) => ({
          key: `${String(fit.wdkStepId)}:${fit.column}`,
          text: fit.sentence,
        }))}
      />
      <Sentences
        testId="facts-retired"
        items={(data.retired ?? []).map((retired) => ({
          key: retired.requirement,
          kind: retired.state,
          text: retired.sentence,
        }))}
      />
      <Sentences
        testId="facts-saved-set"
        items={(data.saved ?? []).map((saved) => ({
          key: `${saved.kind}:${saved.name}`,
          kind: saved.kind,
          text:
            saved.count == null
              ? `Saved ${saved.kind === "gene_set" ? "gene set" : "control set"} ${saved.name}`
              : `Saved ${saved.kind === "gene_set" ? "gene set" : "control set"} ${saved.name}, ${counted(saved.count, saved.recordNoun ?? "gene")}`,
        }))}
      />
      <Sentences
        testId="facts-unsaved-set"
        items={
          data.unsaved == null
            ? []
            : [{ key: "unsaved", kind: "gene_set", text: data.unsaved.sentence }]
        }
      />
      <Sentences
        testId="facts-control-result"
        items={(data.controlResults ?? []).map((result) => ({
          key: result.sentence,
          text: result.sentence,
        }))}
      />
      <RecordsTable title="Records read" sources={sources} testId="facts-source" />
      <RecordsTable
        title="Genes the message names"
        sources={named}
        testId="facts-named-gene"
      />
      <ListedTables listed={data.listed ?? []} />
      <OrthologTables sources={[...sources, ...named]} />
      <MoreValueTables sources={[...sources, ...named]} />
    </Figure>
  );
}
