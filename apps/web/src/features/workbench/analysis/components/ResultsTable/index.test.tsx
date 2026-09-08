/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, fireEvent } from "@testing-library/react";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { createTestWrapper } from "@/lib/query/testing";
import type { ResultsTableInstance } from "./resultsTableFeatures";

const mockGetAttributes = vi.fn();
const mockGetRecords = vi.fn();
const mockGetRecordDetail = vi.fn();

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getAttributes: (...args: unknown[]) => mockGetAttributes(...args),
  getRecords: (...args: unknown[]) => mockGetRecords(...args),
  getRecordDetail: (...args: unknown[]) => mockGetRecordDetail(...args),
}));

vi.mock("./ResultsTableHeader", () => ({
  ResultsTableHeader: ({
    totalCount,
    table,
  }: {
    totalCount: number;
    table: ResultsTableInstance;
  }) => {
    const visibleIds = table
      .getAllLeafColumns()
      .filter((c) => c.getIsVisible())
      .map((c) => c.id)
      .join(",");
    return (
      <div data-testid="header">
        <span data-testid="header-total">count={totalCount}</span>
        <span data-testid="header-cols">cols={visibleIds}</span>
        {table.getAllLeafColumns().map((c) => (
          <button
            key={c.id}
            data-testid={`toggle-${c.id}`}
            onClick={() => c.toggleVisibility()}
          >
            toggle {c.id}
          </button>
        ))}
      </div>
    );
  },
}));

vi.mock("./ResultsTableBody", () => ({
  ResultsTableBody: ({
    table,
    loading,
    onExpandRow,
  }: {
    table: ResultsTableInstance;
    loading: boolean;
    onExpandRow: (row: ClassifiedRecord, expand: boolean) => void;
  }) => {
    const rows = table.getRowModel().rows;
    const sortingKey = table.state.sorting
      .map((s) => `${s.id}:${s.desc ? "d" : "a"}`)
      .join("|");
    return (
      <div data-testid="body" data-loading={loading} data-sorting={sortingKey}>
        <span data-testid="body-rows">records={rows.length}</span>
        <button
          type="button"
          data-testid="sort-first"
          onClick={() => {
            const first = table.getAllLeafColumns().find((c) => c.getCanSort());
            if (first) first.toggleSorting();
          }}
        >
          sort first sortable
        </button>
        {rows.map((row) => (
          <button
            key={row.id}
            data-testid={`expand-${row.id}`}
            onClick={() => onExpandRow(row.original, !row.getIsExpanded())}
            data-expanded={row.getIsExpanded()}
          >
            expand {row.id}
          </button>
        ))}
      </div>
    );
  },
}));

vi.mock("./PaginationControls", () => ({
  PaginationControls: ({
    totalCount,
    table,
  }: {
    totalCount: number;
    table: ResultsTableInstance;
  }) => (
    <div data-testid="pagination" data-page-index={table.state.pagination.pageIndex}>
      <span data-testid="pagination-total">total={totalCount}</span>
      <button data-testid="next-page" onClick={() => table.nextPage()}>
        next
      </button>
    </div>
  ),
}));

import { ResultsTable } from "./index";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";

function makeAttrs(...names: string[]): RecordAttribute[] {
  return names.map((name) => ({
    name,
    displayName: name.replace(/_/g, " "),
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: true,
    isSuggested: false,
  }));
}

function makeRecordsResponse(count: number) {
  return {
    records: Array.from({ length: count }, (_, i) => ({
      id: [{ name: "source_id", value: `GENE_${i}` }],
      attributes: { gene_id: `GENE_${i}`, organism: "Pf" },
    })),
    meta: {
      totalCount: count,
      displayTotalCount: count,
      responseCount: count,
      pagination: { offset: 0, numRecords: 25 },
      attributes: ["gene_id"],
      tables: [],
    },
  };
}

describe("ResultsTable", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderWithQuery(entity: EntityRef) {
    const { Wrapper } = createTestWrapper();
    return render(<ResultsTable entityRef={entity} />, { wrapper: Wrapper });
  }

  it("resets visible columns when entityRef changes", async () => {
    const attrs1 = makeAttrs("gene_id", "organism", "product");
    const attrs2 = makeAttrs("molecular_weight", "go_terms", "ec_number");

    mockGetAttributes.mockImplementation(async (entityRef: EntityRef) => ({
      attributes: entityRef.id === "exp-1" ? attrs1 : attrs2,
      recordType: "gene",
    }));

    mockGetRecords.mockImplementation(async (entityRef: EntityRef) =>
      entityRef.id === "exp-1" ? makeRecordsResponse(3) : makeRecordsResponse(2),
    );

    const entity1: EntityRef = { type: "experiment", id: "exp-1" };
    const entity2: EntityRef = { type: "experiment", id: "exp-2" };

    const { Wrapper } = createTestWrapper();
    const { rerender } = render(<ResultsTable entityRef={entity1} />, {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(screen.getByTestId("header-cols").textContent).toContain("gene_id");
    });

    rerender(<ResultsTable entityRef={entity2} />);

    await waitFor(() => {
      expect(screen.getByTestId("header-cols").textContent).toContain(
        "molecular_weight",
      );
    });

    expect(screen.getByTestId("header-cols").textContent).not.toContain("gene_id");
  });

  it("stops loading when attributes list is empty", async () => {
    mockGetAttributes.mockResolvedValueOnce({
      attributes: [{ name: "hidden", displayName: "Hidden", isDisplayable: false }],
      recordType: "gene",
    });

    const entity: EntityRef = { type: "experiment", id: "exp-1" };
    renderWithQuery(entity);

    await waitFor(() => {
      const body = screen.getByTestId("body");
      expect(body.getAttribute("data-loading")).toBe("false");
    });

    expect(mockGetRecords).not.toHaveBeenCalled();
  });

  it("toggles column visibility via the table instance", async () => {
    const attrs = makeAttrs("gene_id", "organism");
    mockGetAttributes.mockResolvedValue({ attributes: attrs, recordType: "gene" });
    mockGetRecords.mockResolvedValue(makeRecordsResponse(1));

    renderWithQuery({ type: "experiment", id: "exp-1" });

    await waitFor(() => {
      expect(screen.getByTestId("header-cols").textContent).toContain("gene_id");
    });

    fireEvent.click(screen.getByTestId("toggle-gene_id"));

    await waitFor(() => {
      expect(screen.getByTestId("header-cols").textContent).not.toContain("gene_id");
    });
    expect(screen.getByTestId("header-cols").textContent).toContain("organism");
  });

  it("updates sorting state when a sortable column header is toggled", async () => {
    const attrs = makeAttrs("gene_id", "organism");
    mockGetAttributes.mockResolvedValue({ attributes: attrs, recordType: "gene" });
    mockGetRecords.mockResolvedValue(makeRecordsResponse(1));

    renderWithQuery({ type: "experiment", id: "exp-1" });

    await waitFor(() => {
      expect(screen.getByTestId("body-rows").textContent).toBe("records=1");
    });

    fireEvent.click(screen.getByTestId("sort-first"));

    await waitFor(() => {
      const body = screen.getByTestId("body");
      expect(body.getAttribute("data-sorting")).toBe("gene_id:a");
    });

    // Sorting is server-side: the sorting state flows into the fetch call
    await waitFor(() => {
      const lastCall = mockGetRecords.mock.calls.at(-1);
      expect(lastCall?.[1]).toMatchObject({ sort: "gene_id", dir: "ASC" });
    });
  });

  it("advances page and fires a new fetch with the new offset", async () => {
    const attrs = makeAttrs("gene_id");
    mockGetAttributes.mockResolvedValue({ attributes: attrs, recordType: "gene" });
    mockGetRecords.mockResolvedValue({
      ...makeRecordsResponse(1),
      meta: {
        totalCount: 100,
        displayTotalCount: 100,
        responseCount: 25,
        pagination: { offset: 0, numRecords: 25 },
        attributes: ["gene_id"],
        tables: [],
      },
    });

    renderWithQuery({ type: "experiment", id: "exp-1" });

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByTestId("next-page"));

    await waitFor(() => {
      expect(screen.getByTestId("pagination").getAttribute("data-page-index")).toBe(
        "1",
      );
    });

    await waitFor(() => {
      const lastCall = mockGetRecords.mock.calls.at(-1);
      expect(lastCall?.[1]).toMatchObject({ offset: 25, limit: 25 });
    });
  });

  it("expands a row and fetches detail", async () => {
    const attrs = makeAttrs("gene_id");
    mockGetAttributes.mockResolvedValue({ attributes: attrs, recordType: "gene" });
    mockGetRecords.mockResolvedValue(makeRecordsResponse(2));
    mockGetRecordDetail.mockResolvedValue({
      displayName: "GENE_0",
      id: [{ name: "source_id", value: "GENE_0" }],
      recordClassName: "TranscriptRecordClasses.TranscriptRecordClass",
      attributes: { gene_product: "kinase" },
      attributeNames: { gene_product: "Product" },
      tables: {},
      tableErrors: [],
    });

    renderWithQuery({ type: "experiment", id: "exp-1" });

    await waitFor(() => {
      expect(screen.getByTestId("expand-GENE_0")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("expand-GENE_0"));

    await waitFor(() => {
      expect(screen.getByTestId("expand-GENE_0").getAttribute("data-expanded")).toBe(
        "true",
      );
    });

    await waitFor(() => {
      expect(mockGetRecordDetail).toHaveBeenCalledTimes(1);
    });
  });

  it("shows error state when getAttributes fails", async () => {
    mockGetAttributes.mockRejectedValueOnce(new Error("Server error"));

    renderWithQuery({ type: "experiment", id: "exp-1" });

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeTruthy();
    });
  });
});
