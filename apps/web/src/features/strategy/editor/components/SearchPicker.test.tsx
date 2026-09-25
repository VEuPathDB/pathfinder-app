/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import type { RecordType, Search } from "@pathfinder/shared";
import { SearchPicker } from "./SearchPicker";

afterEach(cleanup);

const SEARCHES: Search[] = [
  {
    name: "GenesByMolecularWeight",
    displayName: "Genes by molecular weight",
    recordType: "transcript",
    description: "",
  },
  {
    name: "GenesByTextSearch",
    displayName: "Genes by text search",
    recordType: "transcript",
    description: "",
  },
  {
    name: "GeneListByGo",
    displayName: "Genes by GO term",
    recordType: "transcript",
    description: "",
  },
  {
    name: "PathwayByName",
    displayName: "Pathway by name",
    recordType: "pathway",
    description: "",
  },
];

const RECORD_TYPES: RecordType[] = [
  { name: "transcript", displayName: "Genes" },
  { name: "pathway", displayName: "Metabolic Pathways" },
];

describe("SearchPicker", () => {
  it("opens the picker on trigger click", async () => {
    const user = userEvent.setup();
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value={null}
        onChange={() => {}}
      />,
    );
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByText("Genes by molecular weight")).toBeTruthy();
  });

  it("filters by typed query", async () => {
    const user = userEvent.setup();
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value={null}
        onChange={() => {}}
      />,
    );
    await user.click(screen.getByRole("combobox"));
    const input = screen.getByPlaceholderText(/search/i);
    await user.type(input, "molec");
    expect(screen.getByText("Genes by molecular weight")).toBeTruthy();
    expect(screen.queryByText("Pathway by name")).toBeNull();
  });

  it("says so in one sentence when no search matches", async () => {
    const user = userEvent.setup();
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value={null}
        onChange={() => {}}
      />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.type(screen.getByPlaceholderText(/search/i), "zzzz");
    expect(screen.getByText("No matching searches.")).toBeVisible();
  });

  it("heads each group with the record type's display name", async () => {
    const user = userEvent.setup();
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value={null}
        onChange={() => {}}
      />,
    );
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByText("Genes")).toBeVisible();
    expect(screen.getByText("Metabolic Pathways")).toBeVisible();
    expect(screen.queryByText("transcript")).toBeNull();
    expect(screen.queryByText("pathway")).toBeNull();
  });

  it("fires onChange with the picked search name", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value={null}
        onChange={onChange}
      />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByText("Pathway by name"));
    expect(onChange).toHaveBeenCalledWith("PathwayByName");
  });

  it("renders the selected search label when a value is picked", () => {
    render(
      <SearchPicker
        searches={SEARCHES}
        recordTypes={RECORD_TYPES}
        value="GenesByMolecularWeight"
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Genes by molecular weight")).toBeTruthy();
  });
});
