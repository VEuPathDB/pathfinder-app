"use client";

import { useState } from "react";

import { Textarea } from "@/components/ui/textarea";

import { parseEdaSpec, prettyEdaSpec, type EdaSpecSummary } from "./edaSpecLogic";
import type { ParamWidgetProps } from "./types";

export function EdaSpecParam({ spec, name, field }: ParamWidgetProps) {
  const value = typeof field.state.value === "string" ? field.state.value : "";
  const [draft, setDraft] = useState(() => prettyEdaSpec(value));
  const [seenValue, setSeenValue] = useState(value);
  const [error, setError] = useState<string | null>(null);

  // A value written from outside the editor replaces the draft.
  if (value !== seenValue) {
    setSeenValue(value);
    setDraft(prettyEdaSpec(value));
    setError(null);
  }

  const stored = value.trim() === "" ? null : parseEdaSpec(value);

  const handleChange = (text: string): void => {
    setDraft(text);
    if (text.trim() === "") {
      if (spec.allowEmptyValue === false) {
        setError("The analysis spec is required.");
        return;
      }
      setError(null);
      setSeenValue("");
      field.handleChange("");
      return;
    }
    const parsed = parseEdaSpec(text);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setError(null);
    setSeenValue(parsed.compact);
    field.handleChange(parsed.compact);
  };

  return (
    <div className="space-y-2">
      <StoredSpecView stored={stored} />
      <Textarea
        id={name}
        name={name}
        aria-label="Analysis spec JSON"
        value={draft}
        onChange={(event) => handleChange(event.target.value)}
        onBlur={field.handleBlur}
        spellCheck={false}
        rows={10}
        className="font-mono text-xs"
        aria-invalid={error !== null ? "true" : undefined}
        aria-describedby={error !== null ? `${name}-error` : undefined}
      />
      {error !== null && (
        <p id={`${name}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** The stored value: no spec, a spec that does not parse, or its summary. */
function StoredSpecView({
  stored,
}: {
  stored: ReturnType<typeof parseEdaSpec> | null;
}) {
  if (stored === null) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="eda-spec-summary">
        No analysis spec is set.
      </p>
    );
  }
  if (!stored.ok) {
    return (
      <p className="text-xs text-destructive" data-testid="eda-spec-summary">
        The stored analysis spec does not parse. {stored.error}
      </p>
    );
  }
  return <EdaSpecSummaryView summary={stored.summary} />;
}

function EdaSpecSummaryView({ summary }: { summary: EdaSpecSummary }) {
  const count = summary.computationCount;
  return (
    <div
      className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs"
      data-testid="eda-spec-summary"
    >
      <div className="font-medium text-foreground">
        {summary.displayName === "" ? "Unnamed analysis" : summary.displayName}
      </div>
      <div className="text-muted-foreground">Study {summary.studyId}</div>
      {summary.filters.length > 0 ? (
        <ul className="mt-1 space-y-0.5">
          {summary.filters.map((line, index) => (
            <li key={`${String(index)}-${line}`} data-testid="eda-spec-filter">
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-1 text-muted-foreground">No subset filters</div>
      )}
      <div className="mt-1 text-muted-foreground" data-testid="eda-spec-computations">
        {count} {count === 1 ? "computation" : "computations"}
      </div>
    </div>
  );
}
