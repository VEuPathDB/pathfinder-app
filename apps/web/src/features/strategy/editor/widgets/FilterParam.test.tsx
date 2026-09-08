// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import type { ParamSpec } from "@pathfinder/shared";
import { FilterParam } from "./FilterParam";
import { WidgetTestForm, WidgetTestFormWithValidation } from "./testUtils";

afterEach(cleanup);

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_filter",
    type: "filter",
    displayName: "Test Filter",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("FilterParam — empty value", () => {
  it("renders without throwing for empty string value", () => {
    render(
      <WidgetTestForm name="test_filter" defaultValue="">
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText(/no filters/i)).toBeTruthy();
  });

  it("shows '0 active filters' summary when value is empty", () => {
    render(
      <WidgetTestForm name="test_filter" defaultValue="">
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText(/0 active filters/i)).toBeTruthy();
  });

  it("paints the unrecognized-shape notice from the warning token", () => {
    render(
      <WidgetTestForm name="test_filter" defaultValue="not-a-filter">
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const notice = screen.getByText(/not a recognized filter shape/);
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });
});

describe("FilterParam — populated value", () => {
  const memberFilterValue = JSON.stringify({
    filters: [
      {
        field: "organism",
        type: "string",
        isRange: false,
        includeUnknown: false,
        value: ["P. falciparum", "P. vivax"],
      },
    ],
  });

  it("parses an existing filters JSON value and lists each filter", () => {
    render(
      <WidgetTestForm name="test_filter" defaultValue={memberFilterValue}>
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("organism")).toBeTruthy();
    expect(screen.getByText(/P\. falciparum/)).toBeTruthy();
  });

  it("shows '1 active filter' summary when a filter exists", () => {
    render(
      <WidgetTestForm name="test_filter" defaultValue={memberFilterValue}>
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText(/1 active filter/i)).toBeTruthy();
  });

  it("removes a filter when its remove button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_filter" defaultValue={memberFilterValue}>
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(
      screen.getByRole("button", { name: /remove filter on organism/i }),
    );
    expect(screen.queryAllByText("organism")).toHaveLength(0);
    expect(screen.queryAllByRole("button", { name: /remove filter on/i })).toHaveLength(
      0,
    );
  });

  it("clears all filters when 'Clear all' is clicked", async () => {
    const user = userEvent.setup();
    const twoFilters = JSON.stringify({
      filters: [
        { field: "organism", type: "string", isRange: false, value: ["P. falciparum"] },
        {
          field: "length",
          type: "number",
          isRange: true,
          value: { min: 100, max: 500 },
        },
      ],
    });
    render(
      <WidgetTestForm name="test_filter" defaultValue={twoFilters}>
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("button", { name: /clear all/i }));
    expect(screen.getByText(/no filters/i)).toBeTruthy();
  });
});

describe("FilterParam — JSON editor mode", () => {
  it("opens an editable textarea with current JSON when 'Edit JSON' is clicked", async () => {
    const user = userEvent.setup();
    const value = JSON.stringify({
      filters: [{ field: "x", type: "string", isRange: false, value: ["a"] }],
    });
    render(
      <WidgetTestForm name="test_filter" defaultValue={value}>
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("button", { name: /edit json/i }));
    const textarea = screen.getByRole("textbox", { name: /filter json/i });
    expect(textarea).toBeTruthy();
    expect((textarea as HTMLTextAreaElement).value).toContain('"field": "x"');
  });

  it("rejects invalid JSON and shows an error", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_filter" defaultValue="">
        {(field) => (
          <FilterParam
            spec={makeSpec()}
            name="test_filter"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("button", { name: /edit json/i }));
    const textarea = screen.getByRole("textbox", { name: /filter json/i });
    fireEvent.change(textarea, { target: { value: "{not valid json" } });
    await user.click(screen.getByRole("button", { name: /apply json/i }));
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});

describe("FilterParam — error state", () => {
  it("renders with destructive styling when field has an error", async () => {
    render(
      <WidgetTestFormWithValidation
        name="test_filter"
        defaultValue=""
        validator={() => "Required"}
      >
        {(field) => {
          field.handleBlur();
          return (
            <FilterParam
              spec={makeSpec({ allowEmptyValue: false })}
              name="test_filter"
              options={[]}
              vocabTree={null}
              field={field}
            />
          );
        }}
      </WidgetTestFormWithValidation>,
    );
    await new Promise((r) => setTimeout(r, 30));
    const root = screen.getByTestId("filter-param-root");
    expect(root.getAttribute("data-invalid")).toBe("true");
  });
});
