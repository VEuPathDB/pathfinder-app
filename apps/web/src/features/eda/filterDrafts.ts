import type { EdaEntityResponse } from "@pathfinder/shared/generated/types/EdaEntityResponse";
import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";

const TIME_PART = /T\d{2}:\d{2}:\d{2}/;

/** The service parses only YYYY-MM-DDTHH:mm:ss; a bare date is a 500. */
export function edaDateBound(value: string): string {
  return TIME_PART.test(value) ? value : `${value}T00:00:00`;
}

const HIDDEN_FROM_TREE = ["everywhere", "variableTree"];

/** hideFrom is the study's advice to a UI, and the entity tree is a UI. */
export function isHiddenFromTree(variable: { hideFrom: readonly string[] }): boolean {
  return variable.hideFrom.some((surface) => HIDDEN_FROM_TREE.includes(surface));
}

export type EdaEditableFilterType = "stringSet" | "numberRange" | "dateRange";

/** The three filter types the tab authors. The service derives the rest, and
 * only chat can author them. */
export function editableFilterType(
  filterType: string | null | undefined,
): EdaEditableFilterType | null {
  return filterType === "stringSet" ||
    filterType === "numberRange" ||
    filterType === "dateRange"
    ? filterType
    : null;
}

export type FilterDraft =
  | { kind: "stringSet"; values: string[] }
  | { kind: "numberRange"; min: string; max: string }
  | { kind: "dateRange"; min: string; max: string };

export function isDraftApplicable(draft: FilterDraft): boolean {
  switch (draft.kind) {
    case "stringSet":
      return draft.values.length > 0;
    case "numberRange":
      return (
        Number.isFinite(Number.parseFloat(draft.min)) &&
        Number.isFinite(Number.parseFloat(draft.max))
      );
    case "dateRange":
      return draft.min !== "" && draft.max !== "";
  }
}

export function draftToFilter(
  entityId: string,
  variableId: string,
  draft: FilterDraft,
): EdaFilter {
  switch (draft.kind) {
    case "stringSet":
      return { entityId, variableId, type: "stringSet", stringSet: draft.values };
    case "numberRange":
      return {
        entityId,
        variableId,
        type: "numberRange",
        min: Number.parseFloat(draft.min),
        max: Number.parseFloat(draft.max),
      };
    case "dateRange":
      return {
        entityId,
        variableId,
        type: "dateRange",
        min: edaDateBound(draft.min),
        max: edaDateBound(draft.max),
      };
  }
}

function names(filter: EdaFilter, entityId: string, variableId: string): boolean {
  return filter.entityId === entityId && filter.variableId === variableId;
}

/** Two filters on one variable compose by AND, so an edit replaces. */
export function upsertFilter(
  filters: readonly EdaFilter[],
  next: EdaFilter,
): EdaFilter[] {
  const index = filters.findIndex((f) => names(f, next.entityId, next.variableId));
  if (index === -1) return [...filters, next];
  return filters.map((f, at) => (at === index ? next : f));
}

export function removeFilter(
  filters: readonly EdaFilter[],
  entityId: string,
  variableId: string,
): EdaFilter[] {
  return filters.filter((f) => !names(f, entityId, variableId));
}

export function findFilter(
  filters: readonly EdaFilter[],
  entityId: string,
  variableId: string,
): EdaFilter | null {
  return filters.find((f) => names(f, entityId, variableId)) ?? null;
}

export interface EdaEntityNode {
  entityId: string;
  displayName: string;
  children: EdaEntityNode[];
}

function nodeFor(
  entity: EdaEntityResponse,
  byParent: Map<string, EdaEntityResponse[]>,
): EdaEntityNode {
  return {
    entityId: entity.entityId,
    displayName: entity.displayName,
    children: (byParent.get(entity.entityId) ?? []).map((child) =>
      nodeFor(child, byParent),
    ),
  };
}

/** The wire lists entities flat, each naming its parent. The tab shows the tree. */
export function buildEntityTree(
  entities: readonly EdaEntityResponse[],
): EdaEntityNode | null {
  const known = new Set(entities.map((entity) => entity.entityId));
  const byParent = new Map<string, EdaEntityResponse[]>();
  for (const entity of entities) {
    const parent = entity.parentEntityId;
    if (parent == null || !known.has(parent)) continue;
    byParent.set(parent, [...(byParent.get(parent) ?? []), entity]);
  }
  const root = entities.find(
    (entity) => entity.parentEntityId == null || !known.has(entity.parentEntityId),
  );
  return root === undefined ? null : nodeFor(root, byParent);
}

export function collectEntityIds(root: EdaEntityNode | null): string[] {
  if (root === null) return [];
  return [root.entityId, ...root.children.flatMap((child) => collectEntityIds(child))];
}
