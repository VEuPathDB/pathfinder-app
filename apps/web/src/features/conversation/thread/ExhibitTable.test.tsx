/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ExhibitTable } from "./ExhibitTable";

const COLUMNS = [
  { head: "Control set" },
  { head: "Controls", numeric: true },
  { head: "Returned", numeric: true },
];

describe("ExhibitTable", () => {
  it("lets a keyboard reach and scroll a table wider than its column", () => {
    render(<ExhibitTable testId="controls" columns={COLUMNS} rows={[]} />);

    const region = screen.getByRole("region", {
      name: "Table: Control set, Controls, Returned",
    });
    expect(region.tabIndex).toBe(0);
    expect(region.className).toContain("overflow-x-auto");
  });

  it("heads every column and reads one row per record", () => {
    render(
      <ExhibitTable
        testId="controls"
        columns={COLUMNS}
        rows={[
          { key: "positive", cells: ["Positive", "3", "2"] },
          { key: "negative", cells: ["Negative", "1", "0"] },
        ]}
      />,
    );

    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Control set", "Controls", "Returned"]);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("rules the table above the head, under it and under the body", () => {
    render(<ExhibitTable testId="controls" columns={COLUMNS} rows={[]} />);

    const table = screen.getByTestId("controls");
    expect(table.className).toContain("border-t");
    expect(table.className).toContain("border-b");
    expect(screen.getByRole("columnheader", { name: "Controls" }).className).toContain(
      "border-b",
    );
  });

  it("sets the numbers in the body font, aligned right on one digit width", () => {
    render(
      <ExhibitTable
        testId="controls"
        columns={COLUMNS}
        rows={[{ key: "positive", cells: ["Positive", "3", "2"] }]}
      />,
    );

    const cells = screen.getAllByRole("cell");
    expect(cells[1]?.className).toContain("tabular-nums");
    expect(cells[1]?.className).toContain("text-right");
    expect(screen.getByTestId("controls").className).not.toContain("font-mono");
  });

  it("centers the table in the figure", () => {
    render(<ExhibitTable testId="controls" columns={COLUMNS} rows={[]} />);

    expect(screen.getByTestId("controls").className).toContain("mx-auto");
  });

  it("reads its notes under the table", () => {
    render(
      <ExhibitTable
        testId="controls"
        columns={COLUMNS}
        rows={[]}
        notes={[{ key: "recovered", label: "Recovered", body: "PF3D7_1222600" }]}
      />,
    );

    expect(screen.getByText("Recovered")).toBeInTheDocument();
    expect(screen.getByText("PF3D7_1222600")).toBeInTheDocument();
  });

  describe("a page at a time", () => {
    const ROWS = Array.from({ length: 23 }, (_, index) => ({
      key: `r${String(index)}`,
      cells: [`set ${String(index + 1)}`, "1", "1"],
      testId: "row",
    }));

    function shown(): string[] {
      return screen
        .getAllByTestId("row")
        .map((row) => row.firstChild?.textContent ?? "");
    }

    it("shows the first page and where it sits among the rows", () => {
      render(<ExhibitTable columns={COLUMNS} rows={ROWS} pageSize={10} />);

      expect(shown()).toHaveLength(10);
      expect(shown()[0]).toBe("set 1");
      expect(screen.getByTestId("exhibit-pager")).toHaveTextContent("1-10 of 23");
      expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    });

    it("moves a page forward and back", () => {
      render(<ExhibitTable columns={COLUMNS} rows={ROWS} pageSize={10} />);

      fireEvent.click(screen.getByRole("button", { name: "Next page" }));
      fireEvent.click(screen.getByRole("button", { name: "Next page" }));
      expect(shown()).toEqual(["set 21", "set 22", "set 23"]);
      expect(screen.getByTestId("exhibit-pager")).toHaveTextContent("21-23 of 23");
      expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();

      fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
      expect(screen.getByTestId("exhibit-pager")).toHaveTextContent("11-20 of 23");
    });

    it("draws no pager when every row fits on one page", () => {
      render(<ExhibitTable columns={COLUMNS} rows={ROWS.slice(0, 10)} pageSize={10} />);

      expect(shown()).toHaveLength(10);
      expect(screen.queryAllByTestId("exhibit-pager")).toHaveLength(0);
    });
  });
});
