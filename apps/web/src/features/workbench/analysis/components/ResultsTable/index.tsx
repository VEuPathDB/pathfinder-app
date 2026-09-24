import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useTable,
  type SortingState,
  type ColumnVisibilityState,
  type PaginationState,
  type ExpandedState,
} from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import {
  getAttributes,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";
import { useResultsTableRecords } from "@/features/workbench/analysis/hooks/useResultsTableRecords";
import { useResultsTableDetail } from "@/features/workbench/analysis/hooks/useResultsTableDetail";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { buildColumns, getPrimaryKey } from "./ResultsTableColumns";
import { resultsTableFeatures } from "./resultsTableFeatures";
import { ResultsTableHeader } from "./ResultsTableHeader";
import { ResultsTableBody } from "./ResultsTableBody";
import { PaginationControls } from "./PaginationControls";

interface ResultsTableProps {
  entityRef: EntityRef;
}

const DEFAULT_PAGE_SIZE = 25;
const DEFAULT_VISIBLE_COLUMN_COUNT = 6;

function initialVisibility(attributes: RecordAttribute[]): ColumnVisibilityState {
  const visibility: ColumnVisibilityState = {};
  attributes.forEach((attr, index) => {
    visibility[attr.name] = index < DEFAULT_VISIBLE_COLUMN_COUNT;
  });
  return visibility;
}

export function ResultsTable({ entityRef }: ResultsTableProps) {
  const [attributes, setAttributes] = useState<RecordAttribute[]>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({});
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [expandedRecordId, setExpandedRecordId] = useState<
    ClassifiedRecord["id"] | null
  >(null);

  const entityKey = `${entityRef.type}|${entityRef.id}`;

  const {
    data: fetchedAttributes,
    error: attrQueryError,
    refetch: refetchAttributes,
  } = useQuery({
    queryKey: ["step-attributes", entityKey] as const,
    queryFn: () => getAttributes(entityRef),
    staleTime: 60_000,
    meta: { shownInline: true },
  });

  const attrError = attrQueryError instanceof Error ? attrQueryError.message : null;

  const [prevEntityKey, setPrevEntityKey] = useState(entityKey);
  if (entityKey !== prevEntityKey && fetchedAttributes) {
    setPrevEntityKey(entityKey);
    const displayable = fetchedAttributes.attributes.filter(
      (a) => a.isDisplayable !== false,
    );
    setAttributes(displayable);
    setSorting([]);
    setPagination({ pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE });
    setExpanded({});
    setExpandedRecordId(null);
    setColumnVisibility(initialVisibility(displayable));
  }
  if (fetchedAttributes && attributes.length === 0 && prevEntityKey === entityKey) {
    const displayable = fetchedAttributes.attributes.filter(
      (a) => a.isDisplayable !== false,
    );
    if (displayable.length > 0) {
      setAttributes(displayable);
      setColumnVisibility(initialVisibility(displayable));
    }
  }

  const visibleAttributeNames = attributes
    .filter((a) => columnVisibility[a.name] !== false)
    .map((a) => a.name);

  const recordsState = useResultsTableRecords({
    entityRef,
    attributes: visibleAttributeNames,
    sorting,
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
  });

  const expandedKey =
    typeof expanded === "object" ? (Object.keys(expanded)[0] ?? null) : null;

  const detailState = useResultsTableDetail({
    entityRef,
    expandedKey,
    recordId: expandedRecordId,
  });

  const hasClassification = recordsState.records.some((r) => r.classification != null);
  const columns = buildColumns(attributes, hasClassification);

  const table = useTable({
    features: resultsTableFeatures,
    data: recordsState.records,
    columns,
    state: { sorting, columnVisibility, pagination, expanded },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onColumnVisibilityChange: (updater) => {
      setColumnVisibility(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onPaginationChange: setPagination,
    onExpandedChange: setExpanded,
    getRowId: (row) => getPrimaryKey(row),
    manualSorting: true,
    manualPagination: true,
    manualExpanding: true,
    // Omitted when WDK published no count, so the table does not read a
    // missing total as an empty result.
    ...(recordsState.meta?.totalCount != null
      ? { rowCount: recordsState.meta.totalCount }
      : {}),
    enableSortingRemoval: false,
  });

  const handleExpandRow = (row: ClassifiedRecord, expand: boolean) => {
    if (!expand) {
      setExpanded({});
      setExpandedRecordId(null);
      return;
    }
    const pk = getPrimaryKey(row);
    setExpanded({ [pk]: true });
    setExpandedRecordId(row.id);
  };

  const totalCount = recordsState.meta?.totalCount ?? null;

  const displayError = attrError ?? recordsState.error;
  if (displayError != null && recordsState.records.length === 0) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
        <p className="text-sm text-destructive">{displayError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => {
            if (attrError != null) void refetchAttributes();
            else recordsState.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {displayError != null && (
        <p role="alert" className="text-sm text-destructive">
          {displayError}
        </p>
      )}
      <ResultsTableHeader
        totalCount={totalCount}
        recordType={fetchedAttributes?.recordType ?? null}
        table={table}
        attributes={attributes}
      />

      <ResultsTableBody
        table={table}
        loading={recordsState.loading}
        detail={detailState.detail}
        detailError={detailState.detailError}
        detailLoading={detailState.detailLoading}
        onExpandRow={handleExpandRow}
      />

      <PaginationControls
        table={table}
        totalCount={totalCount}
        loading={recordsState.loading}
      />
    </div>
  );
}
