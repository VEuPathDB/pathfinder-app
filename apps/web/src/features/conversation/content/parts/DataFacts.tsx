"use client";

import type { ReactElement } from "react";
import type {
  ListedFact,
  ParameterFact,
  SourceFact,
  StepFact,
  TurnFacts,
} from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";
import { Sources } from "@/features/conversation/content/parts/FactsSources";
import { useSiteLinkTarget } from "@/lib/hooks/useSiteLinkTarget";

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
  return (
    <li data-testid="facts-param" data-source={fact.source} className="text-xs">
      <span className="text-muted-foreground">{fact.displayName}: </span>
      <span data-testid="facts-param-value">
        {fact.value}
        {label === "" ? null : ` (${label})`}
      </span>
      <span className="ml-1 text-muted-foreground">({SOURCE_LABELS[fact.source]})</span>
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

function Step({
  step,
  noun,
  sources,
  listed,
  target,
}: {
  step: StepFact;
  noun: string;
  sources: SourceFact[];
  listed: ListedFact[];
  target: string;
}): ReactElement {
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
          {withBefore(step.count, step.countBefore, noun)}
        </span>
      </div>
      {(step.reason ?? "") === "" ? null : (
        <div data-testid="facts-step-reason" className="text-xs text-muted-foreground">
          {step.reason}
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
      <Sources sources={sources} testId="facts-source" target={target} />
      {listed.map((listing) => (
        <div
          key={listing.stepId}
          data-testid="facts-listed"
          className="mt-1 break-all text-xs text-muted-foreground"
        >
          Listed from {listing.stepName}:{" "}
          {(listing.records ?? []).map((record, index) => (
            <span key={record.recordId}>
              {index === 0 ? null : ", "}
              <a
                href={record.url}
                target={target}
                rel="noopener noreferrer"
                className="text-primary underline-offset-2 hover:underline"
              >
                {record.recordId}
              </a>
            </span>
          ))}
        </div>
      ))}
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

/** What the turn holds, rendered beside the reply: the steps with their values
 * and counts, what the check measured, and what the turn saved or was refused.
 * The reply restates none of it. */
export function DataFacts({ data }: { data: TurnFacts }): ReactElement {
  const target = useSiteLinkTarget();
  const noun = data.recordNoun ?? "gene";
  const steps = data.steps ?? [];
  const url = data.strategyUrl ?? null;
  const sources = data.sources ?? [];
  const listed = data.listed ?? [];
  const stepIds = new Set(steps.map((step) => step.stepId));
  const ungrouped = sources.filter((s) => !stepIds.has(s.stepId ?? ""));
  return (
    <Figure
      testId="data-facts"
      title={data.draft === true ? "Plan" : "Strategy"}
      caption={null}
    >
      {steps.length === 0 ? null : (
        <ul className="divide-y">
          {steps.map((step) => (
            <Step
              key={step.stepId}
              step={step}
              noun={noun}
              sources={sources.filter((s) => s.stepId === step.stepId)}
              listed={listed.filter((l) => l.stepId === step.stepId)}
              target={target}
            />
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
      {url === null ? null : (
        <a
          data-testid="facts-strategy-link"
          href={url}
          target={target}
          rel="noopener noreferrer"
          className="mt-2 block text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          Open the strategy on the site
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
              : `Saved ${saved.kind === "gene_set" ? "gene set" : "control set"} ${saved.name}, ${counted(saved.count, "gene")}`,
        }))}
      />
      <Sentences
        testId="facts-control-result"
        items={(data.controlResults ?? []).map((result) => ({
          key: result.sentence,
          text: result.sentence,
        }))}
      />
      <Sources sources={ungrouped} testId="facts-source" target={target} />
      <Sources
        sources={data.namedGenes ?? []}
        testId="facts-named-gene"
        target={target}
      />
      <Sentences
        testId="facts-stopped-check"
        items={
          (data.stoppedCheck ?? "") === ""
            ? []
            : [{ key: "stop", text: data.stoppedCheck ?? "" }]
        }
      />
      <Sentences
        testId="facts-refusal"
        items={
          (data.refusal ?? "") === ""
            ? []
            : [{ key: "refusal", text: data.refusal ?? "" }]
        }
      />
    </Figure>
  );
}
