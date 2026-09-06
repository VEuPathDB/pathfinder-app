import { AlertTriangle } from "lucide-react";
import type { VocabEntry } from "../../utils/paramUtils";
import { MAX_CATEGORICAL_CHOICES } from "./types";

export function CategoricalPicker({
  vocab,
  selected,
  onChange,
}: {
  vocab: VocabEntry[];
  selected: Set<string>;
  onChange: (s: Set<string>) => void;
}) {
  const oversized = vocab.length > MAX_CATEGORICAL_CHOICES;
  const displayVocab = oversized ? vocab.slice(0, MAX_CATEGORICAL_CHOICES) : vocab;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          Values to sweep ({selected.size} selected)
        </span>
        <button
          type="button"
          onClick={() => onChange(new Set(displayVocab.map((e) => e.value)))}
          className="text-xs text-primary hover:underline"
        >
          Select all
        </button>
        <button
          type="button"
          onClick={() => onChange(new Set())}
          className="text-xs text-primary hover:underline"
        >
          Deselect all
        </button>
      </div>

      {oversized && (
        <p className="text-xs text-warning">
          <AlertTriangle className="mr-1 inline h-3 w-3" />
          This parameter has {vocab.length} values. Showing first{" "}
          {MAX_CATEGORICAL_CHOICES}.
        </p>
      )}

      <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-card p-2">
        <div className="grid grid-cols-2 gap-1">
          {displayVocab.map((entry) => (
            <label
              key={entry.value}
              className="flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-0.5 text-xs hover:bg-muted/50"
            >
              <input
                type="checkbox"
                checked={selected.has(entry.value)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(entry.value);
                  else next.delete(entry.value);
                  onChange(next);
                }}
                className="h-3 w-3 rounded border-input"
              />
              <span className="truncate text-foreground" title={entry.display}>
                {entry.display}
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
