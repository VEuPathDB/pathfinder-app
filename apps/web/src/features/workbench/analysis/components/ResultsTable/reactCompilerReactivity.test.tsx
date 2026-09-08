/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, describe, expect, it } from "vitest";
import { transformSync } from "@babel/core";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { useTable, type ExpandedState, type SortingState } from "@tanstack/react-table";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import type { ResultsTableBody } from "./ResultsTableBody";
import { buildColumns, getPrimaryKey } from "./ResultsTableColumns";
import { resultsTableFeatures } from "./resultsTableFeatures";

const DIR = resolve(
  process.cwd(),
  "src/features/workbench/analysis/components/ResultsTable",
);

const written: string[] = [];

/** Compiles one source file the way `next build` does, with the React Compiler on. */
function compile(basename: string): string {
  const filename = `${DIR}/${basename}.tsx`;
  const result = transformSync(readFileSync(filename, "utf8"), {
    filename,
    babelrc: false,
    configFile: false,
    presets: [["@babel/preset-typescript", { isTSX: true, allExtensions: true }]],
    plugins: [["babel-plugin-react-compiler", { target: "19" }]],
  });
  const code = result?.code ?? "";
  if (!code.includes("react/compiler-runtime")) {
    throw new Error(`the React Compiler did not memoize ${basename}.tsx`);
  }
  return code;
}

function writeCompiled(basename: string, code: string): string {
  const path = `${DIR}/${basename}.compiled.jsx`;
  writeFileSync(path, code);
  written.push(path);
  return path;
}

const attributes: RecordAttribute[] = [
  {
    name: "gene_id",
    displayName: "Gene ID",
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: true,
    isSuggested: false,
  },
  {
    name: "product",
    displayName: "Product",
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: true,
    isSuggested: false,
  },
];

const record: ClassifiedRecord = {
  displayName: "PF3D7_1234",
  id: [{ name: "source_id", value: "PF3D7_1234" }],
  recordClassName: "transcript",
  attributes: { gene_id: "PF3D7_1234", product: "kinase" },
  tables: {},
  tableErrors: [],
};

// Stable across renders, so the table hands back the same row and header
// objects on a state change, which is the condition the memoization hazard needs.
const data = [record];
const columns = buildColumns(attributes, false);

type CompiledBody = typeof ResultsTableBody;

function Harness({ Body }: { Body: CompiledBody }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const table = useTable({
    features: resultsTableFeatures,
    data,
    columns,
    state: { sorting, expanded },
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    getRowId: (row) => getPrimaryKey(row),
    manualSorting: true,
    manualPagination: true,
    manualExpanding: true,
  });

  return (
    <Body
      table={table}
      loading={false}
      detail={null}
      detailError={null}
      detailLoading={false}
      onExpandRow={(row, expand) =>
        setExpanded(expand ? { [getPrimaryKey(row)]: true } : {})
      }
    />
  );
}

const compiledRecordRow = writeCompiled("RecordRow", compile("RecordRow"));
const compiledBody = writeCompiled(
  "ResultsTableBody",
  compile("ResultsTableBody").replace(
    '"./RecordRow"',
    `"./${compiledRecordRow.split("/").pop()}"`,
  ),
);
const compiled = (await import(/* @vite-ignore */ compiledBody)) as {
  ResultsTableBody: CompiledBody;
};

describe("ResultsTable under the React Compiler", () => {
  afterEach(cleanup);
  afterAll(() => {
    written.forEach((path) => rmSync(path, { force: true }));
  });

  it("keeps every table-state read out of the memoized row component", () => {
    const code = compile("RecordRow");
    expect(code).not.toContain("getIsExpanded");
    expect(code).not.toContain("getVisibleCells");
  });

  it("opens the expanded panel when the row object is unchanged", () => {
    const { container } = render(<Harness Body={compiled.ResultsTableBody} />);

    const dataRow = container.querySelector("tr[data-expanded]");
    expect(dataRow?.getAttribute("data-expanded")).toBe("false");

    fireEvent.click(dataRow!);

    const afterClick = container.querySelector("tr[data-expanded]");
    expect(afterClick?.getAttribute("data-expanded")).toBe("true");
    const panel = container.querySelector<HTMLElement>("td[colspan] > div");
    expect(panel?.style.maxHeight).toBe("500px");
    expect(afterClick?.querySelector(".lucide-chevron-up")).not.toBeNull();
  });

  it("turns the sort indicator when the header object is unchanged", () => {
    const { container } = render(<Harness Body={compiled.ResultsTableBody} />);

    const geneHeader = container.querySelectorAll("thead th")[0];
    expect(geneHeader?.textContent).toBe("Gene ID");
    expect(geneHeader?.querySelector(".lucide-arrow-up-down")).not.toBeNull();

    fireEvent.click(geneHeader!.querySelector("button")!);

    const sorted = container.querySelectorAll("thead th")[0];
    expect(sorted?.querySelector(".lucide-chevron-up")).not.toBeNull();
    expect(sorted?.querySelector(".lucide-arrow-up-down")).toBeNull();
  });
});
