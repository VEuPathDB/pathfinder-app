// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { DateParam } from "./DateParam";
import type { ParamSpec } from "@pathfinder/shared";
import { WidgetTestForm, getInputByLabel } from "./testUtils";

afterEach(cleanup);

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "d",
    type: "date",
    displayName: "D",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("DateParam", () => {
  it("renders an input of type date", () => {
    render(
      <WidgetTestForm name="d" defaultValue="">
        {(field) => (
          <DateParam
            spec={makeSpec()}
            name="d"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = screen.getByLabelText("date input");
    expect(input.getAttribute("type")).toBe("date");
  });

  it("updates value on change", () => {
    render(
      <WidgetTestForm name="d" defaultValue="">
        {(field) => (
          <DateParam
            spec={makeSpec()}
            name="d"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = getInputByLabel("date input");
    fireEvent.change(input, { target: { value: "2024-01-15" } });
    expect(input.value).toBe("2024-01-15");
  });
});
