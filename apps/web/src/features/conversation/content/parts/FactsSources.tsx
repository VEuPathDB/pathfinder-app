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
  target,
}: {
  source: SourceFact;
  testId: string;
  target: string;
}): ReactElement {
  const text = described(source);
  return (
    <li data-testid={testId} data-step-id={source.stepId ?? ""}>
      {text === "" ? null : <span>{text}: </span>}
      <a
        href={source.url}
        target={target}
        rel="noopener noreferrer"
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
  target,
}: {
  sources: SourceFact[];
  testId: string;
  target: string;
}): ReactElement | null {
  if (sources.length === 0) return null;
  return (
    <ul className="mt-2 text-xs">
      {sources.map((source) => (
        <Source key={source.url} source={source} testId={testId} target={target} />
      ))}
    </ul>
  );
}
