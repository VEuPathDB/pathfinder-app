/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ExhibitTable } from "./ExhibitTable";

const COLUMNS = [
  { head: "Control set" },
  { head: "Controls", numeric: true },
  { head: "Returned", numeric: true },
];

describe("ExhibitTable", () => {
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
});
