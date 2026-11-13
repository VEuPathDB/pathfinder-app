"use client";

import { useId } from "react";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import {
  findingViewCertaintyEnum,
  findingViewCheckEnum,
  findingViewErrorTypeEnum,
} from "@strategist/shared/generated/types/FindingView";

import { type FindingFilterState, ORIGINS, oneOf } from "./findingQuery";
import { CERTAINTY_WORDS, ORIGIN_WORDS } from "./words";

interface Choice {
  value: string;
  label: string;
}

function Filter({
  label,
  value,
  choices,
  onChange,
}: {
  label: string;
  value: string | null;
  choices: readonly Choice[];
  onChange: (value: string | null) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(event) => {
          onChange(event.target.value === "" ? null : event.target.value);
        }}
        className="rounded border border-border bg-background px-2 py-1 text-sm"
      >
        <option value="">Any</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function sortedChoices(values: readonly string[]): Choice[] {
  return [...new Set(values)].sort().map((value) => ({ value, label: value }));
}

export function FindingFilters({
  view,
  words,
  state,
  onChange,
  errorFixed = false,
}: {
  view: AuditRunView;
  words: AuditWords;
  state: FindingFilterState;
  onChange: (next: FindingFilterState) => void;
  errorFixed?: boolean;
}) {
  const errors = view.errorTypes.map((type) => ({
    value: type.errorType,
    label: type.title,
  }));
  const screened = [
    ...view.genomes.filter((g) => g.role === "audited").map((g) => g.organism),
    ...view.targets.genomes.map((row) => row.genome),
  ];
  const change = (update: Partial<FindingFilterState>) => {
    onChange({ ...state, ...update, offset: 0 });
  };
  return (
    <fieldset className="mt-2 flex flex-wrap gap-3">
      <legend className="text-sm font-medium">Show findings</legend>
      <Filter
        label="Check"
        value={state.check}
        choices={view.run.checks.map((check) => ({
          value: check,
          label: words.checks[check],
        }))}
        onChange={(value) => {
          change({ check: oneOf(Object.values(findingViewCheckEnum), value) });
        }}
      />
      <Filter
        label="Screened genome"
        value={state.screenedGenome}
        choices={sortedChoices(screened)}
        onChange={(value) => {
          change({ screenedGenome: value });
        }}
      />
      <Filter
        label="Model's genome"
        value={state.genome}
        choices={sortedChoices(
          view.counts.flatMap((row) => (row.genome === "" ? [] : [row.genome])),
        )}
        onChange={(value) => {
          change({ genome: value });
        }}
      />
      {errorFixed ? null : (
        <Filter
          label="Error"
          value={state.errorType}
          choices={errors}
          onChange={(value) => {
            change({
              errorType: oneOf(Object.values(findingViewErrorTypeEnum), value),
            });
          }}
        />
      )}
      <Filter
        label="Certainty"
        value={state.certainty}
        choices={Object.values(findingViewCertaintyEnum).map((certainty) => ({
          value: certainty,
          label: CERTAINTY_WORDS[certainty],
        }))}
        onChange={(value) => {
          change({ certainty: oneOf(Object.values(findingViewCertaintyEnum), value) });
        }}
      />
      <Filter
        label="Source"
        value={state.origin}
        choices={ORIGINS.map((origin) => ({
          value: origin,
          label: ORIGIN_WORDS[origin],
        }))}
        onChange={(value) => {
          change({ origin: oneOf(ORIGINS, value) });
        }}
      />
    </fieldset>
  );
}
