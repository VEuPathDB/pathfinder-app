// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { TimestampParam } from "./TimestampParam";
import type { ParamSpec } from "@pathfinder/shared";
import { WidgetTestForm, getInputByLabel } from "./testUtils";

afterEach(cleanup);

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "ts",
    type: "timestamp",
    displayName: "TS",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("TimestampParam", () => {
  it("renders a datetime-local input", () => {
    render(
      <WidgetTestForm name="ts" defaultValue="">
        {(field) => (
          <TimestampParam
            spec={makeSpec()}
            name="ts"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = screen.getByLabelText(/datetime input/i);
    expect(input.getAttribute("type")).toBe("datetime-local");
  });

  it("updates value on change", () => {
    render(
      <WidgetTestForm name="ts" defaultValue="">
        {(field) => (
          <TimestampParam
            spec={makeSpec()}
            name="ts"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = getInputByLabel("datetime input");
    fireEvent.change(input, { target: { value: "2024-01-15T10:30" } });
    expect(input.value).toBe("2024-01-15T10:30");
  });
});
