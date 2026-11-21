"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import type { ParamSpec } from "@/features/strategy/parameters/spec";
import { isEditable, isShown } from "@/lib/parameters/visibility";
import type { ParamForm } from "../hooks/useParamForm";
import {
  type PhyleticNode,
  type TriState,
  buildPhyleticTree,
  encodeProfilePattern,
  leafStates,
  seedTriStates,
  buildSpeciesLists,
  nextTriState,
  triStateIcon,
  triStateColor,
  collectCodes,
  nodeMatchesSearch,
  defaultExpanded,
} from "./phyleticProfileLogic";

export { claimsPhyleticParams } from "./phyleticProfileLogic";

type PhyleticProfileParamProps = {
  specs: ParamSpec[];
  allSpecs: ParamSpec[];
  form: ParamForm;
};

function findSpecVocab(specs: ParamSpec[], name: string): unknown {
  const spec = specs.find((s) => s.name === name);
  return spec?.vocabulary;
}

type TreeNodeProps = {
  node: PhyleticNode;
  states: Map<string, TriState>;
  expanded: Set<string>;
  searchQuery: string;
  disabled: boolean;
  onToggleState: (code: string) => void;
  onToggleExpand: (code: string) => void;
};

function TreeNodeRow({
  node,
  states,
  expanded,
  searchQuery,
  disabled,
  onToggleState,
  onToggleExpand,
}: TreeNodeProps) {
  const query = searchQuery.toLowerCase();
  if (query && !nodeMatchesSearch(node, query)) return null;

  const state = states.get(node.code) ?? "unconstrained";
  const isExpanded = expanded.has(node.code);
  const hasChildren = node.children.length > 0;
  const indent = (node.depth - 1) * 16;

  return (
    <div>
      <div
        className="flex items-center gap-1 py-0.5 hover:bg-muted/50 rounded px-1"
        style={{ paddingLeft: `${indent}px` }}
        data-node={node.code}
      >
        {hasChildren ? (
          <button
            type="button"
            className="w-4 text-xs text-muted-foreground shrink-0"
            onClick={() => onToggleExpand(node.code)}
            aria-label={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? "\u25BE" : "\u25B8"}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <button
          type="button"
          className={`w-5 text-center font-bold shrink-0 ${triStateColor(state)}`}
          data-toggle={node.code}
          disabled={disabled}
          onClick={() => onToggleState(node.code)}
          aria-label={`Toggle ${node.label}`}
        >
          {triStateIcon(state)}
        </button>
        <span className="text-sm text-foreground truncate">{node.label}</span>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeNodeRow
              key={child.code}
              node={child}
              states={states}
              expanded={expanded}
              searchQuery={searchQuery}
              disabled={disabled}
              onToggleState={onToggleState}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function PhyleticProfileParam({ specs, form }: PhyleticProfileParamProps) {
  const termMapVocab =
    (form.getFieldValue("phyletic_term_map") as unknown) ??
    findSpecVocab(specs, "phyletic_term_map");
  const indentMapVocab =
    (form.getFieldValue("phyletic_indent_map") as unknown) ??
    findSpecVocab(specs, "phyletic_indent_map");

  const tree = buildPhyleticTree(termMapVocab, indentMapVocab);
  const disabled = specs.some((spec) => isShown(spec) && !isEditable(spec));

  const [seeded] = useState(() =>
    seedTriStates(tree, {
      included: form.getFieldValue("included_species"),
      excluded: form.getFieldValue("excluded_species"),
      pattern: String(form.getFieldValue("profile_pattern")),
    }),
  );
  const [states, setStates] = useState<Map<string, TriState>>(seeded.states);

  const [expanded, setExpanded] = useState<Set<string>>(() => defaultExpanded(tree, 3));
  const [searchQuery, setSearchQuery] = useState("");

  const allCodes = collectCodes(tree);
  const summary = (() => {
    let included = 0;
    let excluded = 0;
    let unconstrained = 0;
    for (const code of allCodes) {
      const s = states.get(code) ?? "unconstrained";
      if (s === "include") included++;
      else if (s === "exclude") excluded++;
      else unconstrained++;
    }
    return { included, excluded, unconstrained };
  })();

  const handleToggleState = (code: string) => {
    setStates((prev) => {
      const next = new Map(prev);
      const current = next.get(code) ?? "unconstrained";
      const newState = nextTriState(current);
      if (newState === "unconstrained") {
        next.delete(code);
      } else {
        next.set(code, newState);
      }

      // The pattern matches a census of species, so a clade becomes its leaves.
      // The two lists keep the node the user actually clicked.
      const pattern = encodeProfilePattern(leafStates(next, tree));
      const { included, excluded } = buildSpeciesLists(next);
      form.setFieldValue("profile_pattern", pattern);
      form.setFieldValue("included_species", included);
      form.setFieldValue("excluded_species", excluded);

      return next;
    });
  };

  const handleToggleExpand = (code: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  };

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <Input
        type="text"
        placeholder="Search species..."
        value={searchQuery}
        onChange={(event) => setSearchQuery(event.target.value)}
      />
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>
          <span className="text-muted-foreground font-bold">{"\u25CB"}</span>{" "}
          unconstrained
        </span>
        <span>
          <span className="text-success font-bold">{"\u2713"}</span> include
        </span>
        <span>
          <span className="text-destructive font-bold">{"\u2717"}</span> exclude
        </span>
      </div>
      {seeded.unread.length > 0 && (
        <p data-testid="phyletic-unread" className="text-xs text-warning">
          Stored terms this tree cannot show: {seeded.unread.join(", ")}. They are not
          selected below; the next change rewrites the lists from the tree.
        </p>
      )}
      <div className="max-h-80 overflow-y-auto">
        {tree.map((node) => (
          <TreeNodeRow
            key={node.code}
            node={node}
            states={states}
            expanded={expanded}
            searchQuery={searchQuery}
            disabled={disabled}
            onToggleState={handleToggleState}
            onToggleExpand={handleToggleExpand}
          />
        ))}
      </div>
      <div className="text-xs text-muted-foreground border-t border-border pt-2">
        {summary.included} included &middot; {summary.excluded} excluded &middot;{" "}
        {summary.unconstrained} unconstrained
      </div>
    </div>
  );
}
