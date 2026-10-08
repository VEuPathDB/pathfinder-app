"use client";

import type { ReactElement } from "react";
import type { SourceFact } from "@pathfinder/shared";

/** The record's id and words, and the check's judgement of it. */
function described(source: SourceFact): string {
  const named = [
    source.recordId,
    source.product,
    source.organism,
    ...(source.values ?? []),
  ]
    .filter((text): text is string => (text ?? "") !== "")
    .join(", ");
  const fit = source.fit == null ? "" : ` (the check judged its fit ${source.fit})`;
  return `${named}${fit}`;
}

function Source({
  source,
  testId,
}: {
  source: SourceFact;
  testId: string;
}): ReactElement {
  const text = described(source);
  return (
    <li data-testid={testId} data-step-id={source.stepId ?? ""}>
      {text === "" ? null : <span>{text}: </span>}
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer"
        className="break-all text-primary underline-offset-2 hover:underline"
      >
        {source.url}
      </a>
    </li>
  );
}

export function Sources({
  sources,
  testId,
}: {
  sources: SourceFact[];
  testId: string;
}): ReactElement | null {
  if (sources.length === 0) return null;
  return (
    <ul className="mt-2 text-xs">
      {sources.map((source) => (
        <Source key={source.url} source={source} testId={testId} />
      ))}
    </ul>
  );
}
