"use client";

import type { Step } from "@pathfinder/shared";

type Rationale = NonNullable<Step["rationale"]>;

function score(similarity: number | null | undefined): string {
  return similarity == null ? "not scored" : similarity.toFixed(2);
}

/** Why the step runs what it runs: the search choice against what the catalog
 * answered, or the compute an analysis step's document holds. */
export function StepRationale({ rationale }: { rationale: Rationale }) {
  if (rationale.kind === "analysis") {
    return (
      <div className="mb-3 space-y-1 text-xs" data-testid="step-rationale">
        <p className="font-medium text-foreground">Why these genes</p>
        <p className="text-muted-foreground">{rationale.reason}</p>
      </div>
    );
  }
  const compared = rationale.compared ?? [];
  const query = rationale.query ?? "";
  return (
    <div className="mb-3 space-y-1 text-xs" data-testid="step-rationale">
      <p className="font-medium text-foreground">Why this search</p>
      <p className="text-muted-foreground">{rationale.reason}</p>
      {query !== "" && (
        <p className="text-muted-foreground" data-testid="step-rationale-query">
          catalog query: {query}; this search scored {score(rationale.similarity)} of{" "}
          {rationale.answered ?? 0} answered
        </p>
      )}
      {compared.length > 0 && <p className="text-foreground">Chosen over</p>}
      {compared.length > 0 && (
        <ul className="space-y-0.5 text-muted-foreground">
          {compared.map((search) => (
            <li
              key={search.name}
              className="flex justify-between gap-2"
              data-testid="step-rationale-compared"
            >
              <span className="truncate">{search.displayName}</span>{" "}
              <span className="font-mono">{score(search.similarity)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
