/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { useTable } from "@tanstack/react-table";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { RecordRow } from "./RecordRow";
import { buildColumns, getPrimaryKey } from "./ResultsTableColumns";
import { resultsTableFeatures } from "./resultsTableFeatures";

vi.mock("./ExpandedRowDetail", () => ({
  ExpandedRowDetail: ({ pk, loading }: { pk: string; loading: boolean }) => (
    <div data-testid="expanded-detail" data-loading={loading}>
      {pk}
    </div>
  ),
}));

const attributes: RecordAttribute[] = [
  {
    name: "gene_id",
    displayName: "Gene ID",
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: false,
    isSuggested: false,
  },
  {
    name: "product",
    displayName: "Product",
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: false,
    isSuggested: false,
  },
];

const defaultRecord: ClassifiedRecord = {
  displayName: "PF3D7_1234",
  id: [{ name: "source_id", value: "PF3D7_1234" }],
  recordClassName: "transcript",
  attributes: { gene_id: "PF3D7_1234", product: "kinase" },
  tables: {},
  tableErrors: [],
};

interface HarnessProps {
  record?: ClassifiedRecord;
  includeClassification?: boolean;
  isExpanded?: boolean;
  onToggle?: () => void;
}

function Harness({
  record = defaultRecord,
  includeClassification = false,
  isExpanded = false,
  onToggle = () => {},
}: HarnessProps) {
  const tableColumns = buildColumns(attributes, includeClassification);
  const rowId = getPrimaryKey(record);
  const table = useTable({
    features: resultsTableFeatures,
    data: [record],
    columns: tableColumns,
    getRowId: (row) => getPrimaryKey(row),
    state: { expanded: isExpanded ? { [rowId]: true } : {} },
    onExpandedChange: () => {},
    manualExpanding: true,
  });

  const row = table.getRowModel().rows[0];
  if (!row) {
    throw new Error("Test harness produced no rows");
  }

  return (
    <table>
      <tbody>
        <RecordRow
          pk={row.id}
          cells={row.getVisibleCells()}
          isExpanded={row.getIsExpanded()}
          detail={null}
          detailError={null}
          detailLoading={false}
          onToggle={onToggle}
        />
      </tbody>
    </table>
  );
}

describe("RecordRow", () => {
  afterEach(cleanup);

  it("renders attribute values for each visible column", () => {
    const { container } = render(<Harness />);
    const dataRow = container.querySelector("tr[data-expanded]");
    expect(dataRow).not.toBeNull();
    expect(dataRow!.textContent).toContain("PF3D7_1234");
    expect(screen.getByText("kinase")).toBeTruthy();
  });

  it("calls onToggle when the data row is clicked", () => {
    const onToggle = vi.fn();
    const { container } = render(<Harness onToggle={onToggle} />);
    const dataRows = container.querySelectorAll("tr[data-expanded]");
    expect(dataRows).toHaveLength(1);
    fireEvent.click(dataRows[0]!);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("shows classification badge when the classification column is present", () => {
    const classifiedRecord: ClassifiedRecord = {
      ...defaultRecord,
      classification: "TP" as const,
    };
    render(<Harness record={classifiedRecord} includeClassification />);
    expect(screen.getByText("True Positive")).toBeTruthy();
  });

  it("passes the primary-key row id into the expanded detail", () => {
    render(<Harness isExpanded />);
    const details = screen.getAllByTestId("expanded-detail");
    expect(details.length).toBeGreaterThanOrEqual(1);
    expect(details[0]!.textContent).toContain("PF3D7_1234");
  });
});
