"use client";

import { useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils/cn";
import { isMultiParam } from "@/features/strategy/parameters/spec";
import {
  ancestorsOfSelected,
  derivedExpansion,
  nodeStates,
  summarizeSelection,
  summaryLabel,
  toLeaves,
} from "@/lib/parameters/treeSelection";
import type { VocabNode } from "@/lib/utils/vocab";
import type { ParamWidgetProps, ParamFieldApi } from "./types";
import { CheckboxParam } from "./CheckboxParam";

function nodeMatchesSearch(node: VocabNode, term: string): boolean {
  if (node.label.toLowerCase().includes(term)) return true;
  return node.children?.some((child) => nodeMatchesSearch(child, term)) ?? false;
}

/** Every branch with a search match below it; a search shows each match. */
function searchExpansion(nodes: VocabNode[], term: string): Set<string> {
  const out = new Set<string>();
  const visit = (node: VocabNode): void => {
    if (node.children?.some((child) => nodeMatchesSearch(child, term)) === true) {
      out.add(node.value);
    }
    node.children?.forEach(visit);
  };
  nodes.forEach(visit);
  return out;
}

function branchValues(nodes: VocabNode[]): string[] {
  return nodes.flatMap((node) =>
    node.children != null && node.children.length > 0
      ? [node.value, ...branchValues(node.children)]
      : [],
  );
}

const MAX_CHIPS = 12;

export function TreeBoxParam({
  spec,
  name,
  options,
  vocabTree,
  field,
}: ParamWidgetProps) {
  if (!vocabTree) {
    return (
      <CheckboxParam
        spec={spec}
        name={name}
        options={options}
        vocabTree={null}
        field={field}
      />
    );
  }

  return <TreeBoxInner spec={spec} name={name} vocabTree={vocabTree} field={field} />;
}

function TreeBoxInner({
  spec,
  name,
  vocabTree,
  field,
}: {
  spec: ParamWidgetProps["spec"];
  name: string;
  vocabTree: VocabNode[];
  field: ParamFieldApi;
}) {
  const multi = isMultiParam(spec);

  const [overrides, setOverrides] = useState<Map<string, boolean>>(() => new Map());
  const [searchTerm, setSearchTerm] = useState("");
  const lowerSearch = searchTerm.toLowerCase();

  const errors = field.state.meta.errors;
  const hasError = errors.length > 0;
  const errorMessage = hasError ? String(errors[0]) : null;

  const singleValue =
    !multi && typeof field.state.value === "string" ? field.state.value : "";
  const currentValue: string[] = multi
    ? Array.isArray(field.state.value)
      ? (field.state.value as unknown[]).filter(
          (v): v is string => typeof v === "string",
        )
      : []
    : singleValue === ""
      ? []
      : [singleValue];
  const selectedLeaves = toLeaves(currentValue, vocabTree);
  const selectedSet = new Set(selectedLeaves);
  const states = nodeStates(vocabTree, selectedSet);
  const allLeaves = vocabTree.flatMap((node) => states.get(node.value)?.leaves ?? []);

  const derived = derivedExpansion(vocabTree, states, selectedLeaves, {
    multiPick: multi,
  });
  const searched = lowerSearch
    ? searchExpansion(vocabTree, lowerSearch)
    : new Set<string>();
  const isExpanded = (value: string): boolean =>
    searched.has(value) || (overrides.get(value) ?? derived.has(value));

  const toggleExpand = (value: string) => {
    if (lowerSearch) return;
    setOverrides(new Map(overrides).set(value, !isExpanded(value)));
  };
  // A checkbox click keeps the open state of the branches around it.
  const pinOpenState = (values: string[]) => {
    const next = new Map(overrides);
    for (const value of values) next.set(value, isExpanded(value));
    setOverrides(next);
  };
  const setEveryBranch = (open: boolean) => {
    setOverrides(new Map(branchValues(vocabTree).map((v) => [v, open])));
  };
  const expandSelected = () => {
    const path = ancestorsOfSelected(vocabTree, selectedLeaves);
    setOverrides(new Map([...path].map((v) => [v, true])));
  };

  const toggleBranch = (leaves: string[], allChecked: boolean) => {
    const branchLeaves = new Set(leaves);
    if (allChecked) {
      field.handleChange(selectedLeaves.filter((v) => !branchLeaves.has(v)));
    } else {
      field.handleChange([
        ...selectedLeaves,
        ...leaves.filter((l) => !selectedSet.has(l)),
      ]);
    }
  };

  const toggleLeaf = (leafValue: string) => {
    if (selectedSet.has(leafValue)) {
      field.handleChange(selectedLeaves.filter((v) => v !== leafValue));
    } else {
      field.handleChange([...selectedLeaves, leafValue]);
    }
  };

  function renderNode(node: VocabNode, depth: number, path: string[]) {
    if (lowerSearch && !nodeMatchesSearch(node, lowerSearch)) {
      return null;
    }

    const isBranch = Boolean(node.children != null && node.children.length > 0);
    const expanded = isExpanded(node.value);
    const state = states.get(node.value);
    const checked = state?.checked ?? false;

    return (
      <div key={node.value}>
        <div
          data-node-row
          className="flex items-center gap-1 py-0.5"
          style={{ paddingLeft: depth * 20 }}
        >
          {isBranch ? (
            <button
              type="button"
              onClick={() => toggleExpand(node.value)}
              className="w-4 h-4 flex items-center justify-center text-muted-foreground"
              aria-label={expanded ? "Collapse" : "Expand"}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
                  transition: "transform 0.15s",
                }}
              >
                <path d="M4 2 L8 6 L4 10" />
              </svg>
            </button>
          ) : (
            <span className="w-4" />
          )}
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            {multi ? (
              <Checkbox
                checked={checked}
                onCheckedChange={() => {
                  pinOpenState(isBranch ? [...path, node.value] : path);
                  if (isBranch) toggleBranch(state?.leaves ?? [], checked === true);
                  else toggleLeaf(node.value);
                }}
                onBlur={field.handleBlur}
                aria-label={node.label}
              />
            ) : !isBranch ? (
              <RadioGroupItem value={node.value} aria-label={node.label} />
            ) : null}
            {node.label}
          </label>
        </div>
        {isBranch &&
          expanded &&
          node.children?.map((child) =>
            renderNode(child, depth + 1, [...path, node.value]),
          )}
      </div>
    );
  }

  const selectedCount = allLeaves.filter((v) => selectedSet.has(v)).length;
  const summary = summarizeSelection(vocabTree, states, selectedLeaves);

  const treeBody = (
    <div
      aria-invalid={hasError ? "true" : undefined}
      aria-describedby={hasError ? `${name}-error` : undefined}
      className={cn(
        "rounded-md border bg-card text-sm",
        hasError ? "border-destructive/30 bg-destructive/5" : "border-border",
      )}
    >
      <div className="p-2 border-b border-border">
        <Input
          type="text"
          placeholder="Search..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
        />
        <div className="mt-1.5 flex gap-3 text-xs">
          <TreeLink onClick={expandSelected}>Expand selected</TreeLink>
          <TreeLink onClick={() => setEveryBranch(false)}>Collapse all</TreeLink>
          <TreeLink onClick={() => setEveryBranch(true)}>Expand all</TreeLink>
        </div>
      </div>
      <div className="max-h-64 overflow-y-auto p-2">
        {vocabTree.map((node) => renderNode(node, 0, []))}
      </div>
      {multi && (
        <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 border-t border-border text-xs text-muted-foreground">
          <span>
            {selectedCount} of {allLeaves.length} selected
          </span>
          {summary.slice(0, MAX_CHIPS).map((item) => (
            <span
              key={item.value}
              data-testid="treebox-summary-chip"
              className="rounded-sm bg-muted px-1.5 py-0.5 text-foreground"
            >
              {summaryLabel(item)}
            </span>
          ))}
          {summary.length > MAX_CHIPS && (
            <span>+{summary.length - MAX_CHIPS} more</span>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div>
      {multi ? (
        treeBody
      ) : (
        <RadioGroup
          value={singleValue}
          onValueChange={(next) => field.handleChange(next)}
        >
          {treeBody}
        </RadioGroup>
      )}
      {hasError && errorMessage != null && (
        <p id={`${name}-error`} role="alert" className="mt-1 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}

function TreeLink({ onClick, children }: { onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-primary underline-offset-2 hover:underline"
    >
      {children}
    </button>
  );
}
