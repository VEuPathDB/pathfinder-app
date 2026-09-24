"use client";

import type { ReactElement, ReactNode } from "react";

import type {
  ControlSetSummary,
  ControlTestResults,
  TestedParameter,
} from "@pathfinder/shared";

import { CountOfIds } from "@/features/conversation/thread/CountOfIds";
import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const RATE_DIGITS = 2;
const IDS_SHOWN = 8;

const COLUMNS = [
  { head: "Control set" },
  { head: "Controls", numeric: true },
  { head: "Returned", numeric: true },
  { head: "Measure" },
  { head: "Value", numeric: true },
] as const;

function rate(value: number | null | undefined): string | null {
  return value == null ? null : value.toFixed(RATE_DIGITS);
}

function hits(set: ControlSetSummary): string {
  return `${set.intersectionCount.toLocaleString()} of ${set.controlsCount.toLocaleString()}`;
}

/** What the tested step is called: the name WDK gives it, or the step itself
 * when the run could not read that name. */
function targetName(data: ControlTestResults): string {
  const label = data.targetLabel ?? "";
  if (label !== "") return label;
  return data.targetStepId == null
    ? "the tested step"
    : `step ${String(data.targetStepId)}`;
}

function setClause(set: ControlSetSummary, kind: "positive" | "negative"): string {
  const verb = kind === "positive" ? "recovered" : "returned";
  const measured = kind === "positive" ? rate(set.recall) : rate(set.falsePositiveRate);
  const name = kind === "positive" ? "recall" : "false-positive rate";
  const tail = measured === null ? "" : ` (${name} ${measured})`;
  return `${hits(set)} ${kind} controls ${verb}${tail}`;
}

function caption(data: ControlTestResults): string {
  const clauses: string[] = [
    `target ${(data.targetEstimatedSize ?? 0).toLocaleString()} records`,
  ];
  if (data.positive != null) clauses.push(setClause(data.positive, "positive"));
  if (data.negative != null) clauses.push(setClause(data.negative, "negative"));
  return `Control tests on ${targetName(data)}: ${clauses.join(", ")}.`;
}

function GeneIds({ ids }: { ids: readonly string[] }): ReactElement {
  const shown = ids.slice(0, IDS_SHOWN);
  const rest = ids.length - shown.length;
  return (
    <span>
      <span className="font-mono">{shown.join(", ")}</span>
      {rest > 0 ? (
        <span className="text-muted-foreground">{` and ${rest.toLocaleString()} more`}</span>
      ) : null}
    </span>
  );
}

/** The ids behind a set's own size: the controls the target returned and the
 * ones it left out. */
function setIds(set: ControlSetSummary): string[] {
  return [...(set.hitIds ?? []), ...(set.missedIds ?? [])];
}

function controlRow(set: ControlSetSummary, kind: "positive" | "negative"): ExhibitRow {
  const measure = kind === "positive" ? "Recall" : "False-positive rate";
  const measured = kind === "positive" ? rate(set.recall) : rate(set.falsePositiveRate);
  const controls = `${kind} controls`;
  return {
    key: kind,
    cells: [
      kind === "positive" ? "Positive" : "Negative",
      <CountOfIds
        key="controls"
        count={set.controlsCount}
        ids={setIds(set)}
        noun={controls}
      />,
      <CountOfIds
        key="returned"
        count={set.intersectionCount}
        ids={set.hitIds ?? []}
        noun={`${controls} the target returned`}
      />,
      measure,
      measured ?? "-",
    ],
  };
}

function rows(data: ControlTestResults): ExhibitRow[] {
  const built: ExhibitRow[] = [];
  if (data.positive != null) built.push(controlRow(data.positive, "positive"));
  if (data.negative != null) built.push(controlRow(data.negative, "negative"));
  return built;
}

/** The ids behind the counts, so a reader can check a gene by name. */
function notes(data: ControlTestResults): ExhibitNote[] {
  const built: ExhibitNote[] = [];
  const recovered = data.positive?.hitIds ?? [];
  const missed = data.positive?.missedIds ?? [];
  const unexpected = data.negative?.hitIds ?? [];
  const excluded = data.negative?.missedIds ?? [];
  if (recovered.length > 0) {
    built.push({
      key: "recovered",
      label: "Positives recovered:",
      body: <GeneIds ids={recovered} />,
    });
  }
  if (missed.length > 0) {
    built.push({
      key: "missed",
      label: "Positives missed:",
      body: <GeneIds ids={missed} />,
    });
  }
  if (unexpected.length > 0) {
    built.push({
      key: "unexpected",
      label: "Negatives returned:",
      body: <GeneIds ids={unexpected} />,
    });
  }
  if (excluded.length > 0) {
    built.push({
      key: "excluded",
      label: "Negatives excluded:",
      body: <GeneIds ids={excluded} />,
    });
  }
  return built;
}

function Criterion({ parameter }: { parameter: TestedParameter }): ReactElement {
  return (
    <div className="flex gap-1.5">
      <dt className="shrink-0 text-muted-foreground">{`${parameter.label}:`}</dt>
      <dd className="min-w-0 break-words text-foreground">{parameter.value}</dd>
    </div>
  );
}

/** The tested step and its size, naming the step once. */
function testedLine(data: ControlTestResults): string {
  const size = `${(data.targetEstimatedSize ?? 0).toLocaleString()} records`;
  const label = data.targetLabel ?? "";
  if (label === "") return `${targetName(data)}, ${size}`;
  const step = data.targetStepId == null ? "" : ` (step ${String(data.targetStepId)})`;
  return `${label}${step}, ${size}`;
}

/** What was tested, above the numbers: the step, its size and its criteria. */
function TestedStep({ data }: { data: ControlTestResults }): ReactNode {
  const parameters = data.targetParameters ?? [];
  return (
    <dl className="mb-3 space-y-0.5 text-[11px] leading-relaxed">
      <div className="flex gap-1.5">
        <dt className="shrink-0 text-muted-foreground">Tested step:</dt>
        <dd className="min-w-0 text-foreground">{testedLine(data)}</dd>
      </div>
      {parameters.map((parameter) => (
        <Criterion key={parameter.label} parameter={parameter} />
      ))}
    </dl>
  );
}

export function DataControlTestResults({ data }: { data: ControlTestResults }) {
  const chat = useChatHelpers();
  return (
    <Figure
      testId="data-control-test-results"
      title="Control tests"
      caption={caption(data)}
      exhibit={{ kind: "table", number: tableNumberFor(chat.messages, data) }}
    >
      <TestedStep data={data} />
      <ExhibitTable columns={COLUMNS} rows={rows(data)} notes={notes(data)} />
    </Figure>
  );
}
