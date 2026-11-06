"use client";

import { useState } from "react";
import { z } from "zod";
import { FilterIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  EMPTY_FILTER_VALUE,
  FilterEntrySchema,
  FilterValueObjectSchema,
  fieldTypeLabel,
  summarizeFilterValue,
  type FilterEntry,
  type FilterValueObject,
} from "./filterParamLogic";

interface FilterListProps {
  filters: FilterEntry[];
  onRemove: (index: number) => void;
}

export function FilterList({ filters, onRemove }: FilterListProps) {
  if (filters.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-center text-xs text-muted-foreground">
        No filters configured. Use Edit JSON to add one, or wait for the inline facet
        picker (coming with backend ontology metadata).
      </div>
    );
  }
  return (
    <ul className="space-y-1.5">
      {filters.map((filter, idx) => (
        <li
          key={`${filter.field}-${String(idx)}`}
          className="flex items-start gap-2 rounded-md border border-border bg-card p-2 text-sm"
        >
          <FilterIcon
            className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="font-medium text-foreground">{filter.field}</span>
              <Badge variant="outline" className="px-1.5 py-0 text-[0.625rem]">
                {fieldTypeLabel(filter)}
              </Badge>
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {summarizeFilterValue(filter)}
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-6 shrink-0"
            aria-label={`Remove filter on ${filter.field}`}
            onClick={() => onRemove(idx)}
          >
            <XIcon className="size-3.5" />
          </Button>
        </li>
      ))}
    </ul>
  );
}

interface FilterJsonEditorProps {
  initialJson: string;
  onApply: (parsed: FilterValueObject) => void;
  onCancel: () => void;
  name: string;
}

export function FilterJsonEditor({
  initialJson,
  onApply,
  onCancel,
  name,
}: FilterJsonEditorProps) {
  const [draft, setDraft] = useState(initialJson);
  const [error, setError] = useState<string | null>(null);

  const apply = () => {
    if (draft.trim() === "") {
      onApply(EMPTY_FILTER_VALUE);
      setError(null);
      return;
    }
    try {
      const parsedRaw = JSON.parse(draft) as unknown;
      const result = FilterValueObjectSchema.safeParse(parsedRaw);
      if (!result.success) {
        const arrResult = z.array(FilterEntrySchema).safeParse(parsedRaw);
        if (arrResult.success) {
          onApply({ filters: arrResult.data });
          setError(null);
          return;
        }
        setError(
          "JSON is valid but does not match the expected shape: { filters: [...] }",
        );
        return;
      }
      onApply(result.data);
      setError(null);
    } catch (parseError) {
      setError(parseError instanceof Error ? parseError.message : "Invalid JSON");
    }
  };

  return (
    <div className="space-y-2">
      <Textarea
        id={`${name}-json`}
        aria-label="Filter JSON"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        rows={8}
        className="font-mono text-xs"
        placeholder='{"filters": [{"field": "organism", "type": "string", "isRange": false, "value": ["P. falciparum"]}]}'
      />
      {error !== null && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" onClick={apply}>
          Apply JSON
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <a
          href="https://github.com/VEuPathDB/web-monorepo/blob/main/packages/libs/wdk-client/src/Components/AttributeFilter/Types.ts"
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Filter shape reference
        </a>
      </div>
    </div>
  );
}
