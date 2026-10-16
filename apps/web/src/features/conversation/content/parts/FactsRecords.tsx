"use client";

import type { ReactElement } from "react";
import type { ListedFact, SourceFact } from "@pathfinder/shared";

import { ExhibitTable } from "@/features/conversation/thread/ExhibitTable";

const PAGE_SIZE = 10;
const ROW_WORDS = 3;
const RECORD_COLUMNS = [
  { head: "Gene" },
  { head: "Product" },
  { head: "Organism" },
  { head: "Step" },
  { head: "Details" },
  { head: "Fit" },
];
const ORTHOLOG_COLUMNS = [{ head: "Gene" }, { head: "Organism" }];
const LISTED_COLUMNS = [{ head: "Gene" }];
const VALUE_COLUMNS = [{ head: "Value" }];

function RecordLink({ url, text }: { url: string; text: string }): ReactElement {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="whitespace-nowrap text-primary underline-offset-2 hover:underline"
    >
      {text}
    </a>
  );
}

function details(source: SourceFact): string {
  const count = (source.orthologs ?? []).length;
  const values = source.values ?? [];
  const words = values.slice(0, ROW_WORDS);
  if (values.length > ROW_WORDS)
    words.push(`${(values.length - ROW_WORDS).toLocaleString()} more`);
  if (count > 0)
    words.push(`${count.toLocaleString()} ${count === 1 ? "ortholog" : "orthologs"}`);
  return words.join(", ");
}

function Titled({
  title,
  testId,
  children,
}: {
  title: string;
  testId?: string;
  children: ReactElement;
}): ReactElement {
  return (
    <div data-testid={testId} className="mt-3">
      <div className="mb-1 font-medium">{title}</div>
      {children}
    </div>
  );
}

export function RecordsTable({
  title,
  sources,
  testId,
}: {
  title: string;
  sources: readonly SourceFact[];
  testId: string;
}): ReactElement | null {
  if (sources.length === 0) return null;
  return (
    <Titled title={title}>
      <ExhibitTable
        columns={RECORD_COLUMNS}
        pageSize={PAGE_SIZE}
        rows={sources.map((source, index) => ({
          key: `${source.url}-${String(index)}`,
          testId,
          cells: [
            <RecordLink
              key="gene"
              url={source.url}
              text={
                (source.recordId ?? "") === "" ? source.url : (source.recordId ?? "")
              }
            />,
            source.product ?? "",
            source.organism ?? "",
            source.stepName ?? "",
            details(source),
            source.fit ?? "",
          ],
        }))}
      />
    </Titled>
  );
}

export function OrthologTables({
  sources,
}: {
  sources: readonly SourceFact[];
}): ReactElement[] {
  return sources
    .filter((source) => (source.orthologs ?? []).length > 0)
    .map((source) => (
      <Titled
        key={source.url}
        title={`Orthologs of ${source.recordId ?? source.url}`}
        testId="facts-orthologs"
      >
        <ExhibitTable
          columns={ORTHOLOG_COLUMNS}
          pageSize={PAGE_SIZE}
          rows={(source.orthologs ?? []).map((ortholog, index) => ({
            key: `${ortholog.geneId}-${String(index)}`,
            testId: "facts-ortholog",
            cells: [ortholog.geneId, ortholog.organism ?? ""],
          }))}
        />
      </Titled>
    ));
}

export function ListedTables({
  listed,
}: {
  listed: readonly ListedFact[];
}): ReactElement[] {
  return listed.map((listing) => (
    <Titled
      key={listing.stepId}
      title={`Listed from ${listing.stepName ?? listing.stepId}`}
      testId="facts-listed"
    >
      <ExhibitTable
        columns={LISTED_COLUMNS}
        pageSize={PAGE_SIZE}
        rows={(listing.records ?? []).map((record) => ({
          key: record.recordId,
          cells: [<RecordLink key="gene" url={record.url} text={record.recordId} />],
        }))}
      />
    </Titled>
  ));
}

export function MoreValueTables({
  sources,
}: {
  sources: readonly SourceFact[];
}): ReactElement[] {
  return sources
    .filter((source) => (source.values ?? []).length > ROW_WORDS)
    .map((source) => (
      <Titled
        key={source.url}
        title={`More of ${source.recordId ?? source.url}`}
        testId="facts-more-values"
      >
        <ExhibitTable
          columns={VALUE_COLUMNS}
          pageSize={PAGE_SIZE}
          rows={(source.values ?? []).slice(ROW_WORDS).map((value, index) => ({
            key: `${value}-${String(index)}`,
            testId: "facts-more-value",
            cells: [value],
          }))}
        />
      </Titled>
    ));
}
