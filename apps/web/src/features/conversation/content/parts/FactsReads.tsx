"use client";

import type { ReactElement } from "react";
import type {
  ReadFact,
  ComparisonFact,
  ListedRecord,
  MembershipFact,
} from "@pathfinder/shared";

import { RecordLink, Titled } from "./FactsRecords";

function counted(count: number, noun: string): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}

function LinkedIds({
  title,
  ids,
  records,
}: {
  title: string;
  ids: readonly string[];
  records: readonly ListedRecord[];
}): ReactElement | null {
  if (ids.length === 0) return null;
  const pages = new Map(records.map((record) => [record.recordId, record.url]));
  return (
    <li className="text-xs">
      <span className="text-muted-foreground">{title}: </span>
      {ids.map((id, index) => {
        const url = pages.get(id);
        return (
          <span key={id}>
            {index === 0 ? null : ", "}
            {url === undefined ? id : <RecordLink url={url} text={id} />}
          </span>
        );
      })}
    </li>
  );
}

function Membership({ fact }: { fact: MembershipFact }): ReactElement {
  const records = fact.records ?? [];
  const held = fact.held ?? [];
  const unread = fact.unread ?? [];
  const judged = new Set([...held, ...unread]);
  const notHeld = records
    .map((record) => record.recordId)
    .filter((id) => !judged.has(id));
  const label = fact.searchLabel;
  return (
    <Titled title={`Asked of ${label}`} testId="facts-membership">
      <ul>
        <LinkedIds title={`Held by ${label}`} ids={held} records={records} />
        <LinkedIds title={`Not held by ${label}`} ids={notHeld} records={records} />
        <LinkedIds title={`Past the read of ${label}`} ids={unread} records={records} />
      </ul>
    </Titled>
  );
}

export function MembershipFacts({
  memberships,
}: {
  memberships: readonly MembershipFact[];
}): ReactElement[] {
  return memberships.map((fact, index) => (
    <Membership key={`${fact.searchLabel}-${String(index)}`} fact={fact} />
  ));
}

export function ReadFacts({ reads }: { reads: readonly ReadFact[] }): ReactElement[] {
  return reads.map((read, index) => (
    <Titled
      key={`${read.title}-${String(index)}`}
      title={read.title}
      testId="facts-read"
    >
      <ul>
        {(read.rows ?? []).map((row, rowIndex) => (
          <li
            key={`${row.label}-${String(rowIndex)}`}
            data-testid="facts-read-row"
            className="text-xs"
          >
            <span className="text-muted-foreground">{row.label}: </span>
            {row.value}
          </li>
        ))}
      </ul>
    </Titled>
  ));
}

export function CountFacts({
  comparisons,
  noun,
}: {
  comparisons: readonly ComparisonFact[];
  noun: string;
}): ReactElement | null {
  const counts = comparisons
    .filter((comparison) => comparison.onItsCard === false)
    .flatMap((comparison) => comparison.variants ?? []);
  if (counts.length === 0) return null;
  return (
    <ul className="mt-2 text-xs">
      {counts.map((variant, index) => (
        <li key={`${variant.label}-${String(index)}`} data-testid="facts-count">
          {`${variant.label}: ${counted(variant.geneCount, noun)}`}
        </li>
      ))}
    </ul>
  );
}
