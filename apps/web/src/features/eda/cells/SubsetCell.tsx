"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { EdaEntityCount } from "@pathfinder/shared";
import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";

import { Spinner } from "@/components/ui/spinner";
import {
  countEdaSubset,
  edaStudyDetailOptions,
  patchConversationEda,
} from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { selectEffectiveFilters, useEdaStore } from "@/state/eda";

import {
  buildEntityTree,
  collectEntityIds,
  removeFilter,
  upsertFilter,
  type EdaEntityNode,
} from "../filterDrafts";
import { CellShell } from "./CellShell";
import { DistributionSparkline } from "./DistributionSparkline";
import { EntityTree } from "./EntityTree";
import { FilterChip } from "./FilterChip";

const COUNT_FAILED = "Subset count failed";
const STUDY_FAILED = "Could not read the study";

function entityNames(root: EdaEntityNode | null): Map<string, string> {
  if (root === null) return new Map();
  const names = new Map<string, string>([[root.entityId, root.displayName]]);
  for (const child of root.children) {
    for (const [id, name] of entityNames(child)) names.set(id, name);
  }
  return names;
}

function variableName(
  variables: readonly EdaVariableResponse[],
  filter: EdaFilter,
): string {
  const found = variables.find(
    (variable) =>
      variable.entityId === filter.entityId &&
      variable.variableId === filter.variableId,
  );
  return found?.displayName ?? filter.variableId;
}

export function SubsetCell({
  siteId,
  conversationId,
}: {
  siteId: string;
  conversationId: string;
}) {
  const binding = useEdaStore((s) => s.binding);
  const analysis = useEdaStore((s) => s.analysis);
  const filters = useEdaStore(selectEffectiveFilters);
  const setLocalFilters = useEdaStore((s) => s.setLocalFilters);
  const applyAnalysisState = useEdaStore((s) => s.applyAnalysisState);

  const [liveCounts, setLiveCounts] = useState<EdaEntityCount[] | null>(null);
  const [countError, setCountError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set<string>());
  const [seededRoot, setSeededRoot] = useState<string | null>(null);
  const [openVariableId, setOpenVariableId] = useState<string | null>(null);
  const [selectedVariableId, setSelectedVariableId] = useState<string | null>(null);

  const datasetId = binding?.datasetId ?? "";
  const detail = useQuery({
    ...edaStudyDetailOptions(siteId, datasetId),
    enabled: datasetId !== "",
    meta: { shownInline: true },
  });

  const tree = buildEntityTree(detail.data?.entities ?? []);
  if (tree !== null && seededRoot !== tree.entityId) {
    setSeededRoot(tree.entityId);
    setExpanded(new Set([tree.entityId]));
  }

  const edit = useMutation({
    mutationFn: async (next: EdaFilter[]) => {
      const counted = await Promise.all(
        collectEntityIds(tree).map((entityId) =>
          countEdaSubset({ siteId, datasetId, entityId, filters: next }),
        ),
      );
      const patched = await patchConversationEda(conversationId, {
        action: "set-filters",
        filters: next,
      });
      return { counted, patched };
    },
    onMutate: (next) => {
      setCountError(null);
      setLocalFilters(next);
    },
    onSuccess: ({ counted, patched }) => {
      const names = entityNames(tree);
      setLiveCounts(
        counted.map((row) => ({
          ...row,
          entityDisplayName: names.get(row.entityId) ?? row.entityId,
        })),
      );
      if (patched.analysis !== null) applyAnalysisState(patched.analysis);
    },
    onError: (error) => {
      setLocalFilters(null);
      setCountError(toUserMessage(error, COUNT_FAILED));
    },
  });

  const variables = detail.data?.variables ?? [];
  const counts = liveCounts ?? analysis?.entityCounts ?? [];
  const selected =
    variables.find((variable) => variable.variableId === selectedVariableId) ?? null;

  return (
    <CellShell title="Subset" subtitle={null} testId="eda-subset-cell">
      <div className="flex gap-4">
        <div className="w-72 shrink-0">
          {detail.isPending ? <Spinner className="size-4" /> : null}
          {detail.error != null ? (
            <p
              data-testid="eda-subset-study-error"
              className="text-xs text-destructive"
            >
              {toUserMessage(detail.error, STUDY_FAILED)}
            </p>
          ) : null}
          {tree !== null ? (
            <ul>
              <EntityTree
                node={tree}
                depth={0}
                counts={counts}
                variables={variables}
                filters={filters}
                expanded={expanded}
                openVariableId={openVariableId}
                onToggleEntity={(entityId) =>
                  setExpanded((current) => {
                    const next = new Set(current);
                    if (!next.delete(entityId)) next.add(entityId);
                    return next;
                  })
                }
                onOpenVariable={(variableId) => {
                  setOpenVariableId(variableId);
                  if (variableId !== null) setSelectedVariableId(variableId);
                }}
                onApply={(filter) => {
                  setOpenVariableId(null);
                  edit.mutate(upsertFilter(filters, filter));
                }}
              />
            </ul>
          ) : null}
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {filters.map((filter) => (
              <FilterChip
                key={`${filter.entityId}-${filter.variableId}`}
                filter={filter}
                displayName={variableName(variables, filter)}
                onRemove={() =>
                  edit.mutate(removeFilter(filters, filter.entityId, filter.variableId))
                }
              />
            ))}
          </div>
          {analysis !== null && analysis.unparsedFilterCount > 0 ? (
            <p
              data-testid="eda-subset-unparsed-filters"
              className="text-[11px] text-muted-foreground"
            >
              {`${String(analysis.unparsedFilterCount)} ${analysis.unparsedFilterCount === 1 ? "filter" : "filters"} on this analysis cannot be edited here. Change them through chat.`}
            </p>
          ) : null}
          {countError !== null ? (
            <p
              data-testid="eda-subset-count-error"
              className="text-xs text-destructive"
            >
              {countError}
            </p>
          ) : null}
          {selected !== null ? (
            <DistributionSparkline
              siteId={siteId}
              datasetId={datasetId}
              variable={selected}
              filters={filters}
            />
          ) : null}
        </div>
      </div>
    </CellShell>
  );
}
