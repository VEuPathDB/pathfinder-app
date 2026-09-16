// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { TypeAheadParam } from "./TypeAheadParam";
import type { ParamSpec } from "@pathfinder/shared";
import type { VocabOption } from "@/lib/utils/vocab";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

const sampleOptions: VocabOption[] = [
  { label: "Apple", value: "apple" },
  { label: "Banana", value: "banana" },
  { label: "Cherry", value: "cherry" },
];

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_param",
    type: "string",
    displayName: "Test",
    displayType: "typeahead",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("TypeAheadParam (single-pick - shadcn Combobox)", () => {
  it("renders a combobox trigger", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <TypeAheadParam
            spec={makeSpec()}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("opens, lists and picks an option", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <TypeAheadParam
            spec={makeSpec()}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Banana")).toBeTruthy();
    await user.click(screen.getByText("Banana"));
    expect(screen.getByText("Banana")).toBeTruthy();
  });

  it("shows the selected label when value is set initially", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue="cherry">
        {(field) => (
          <TypeAheadParam
            spec={makeSpec()}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("Cherry")).toBeTruthy();
  });
});

describe("TypeAheadParam (multi-pick - shadcn Combobox multi)", () => {
  it("renders chips for selected values", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={["apple", "cherry"]}>
        {(field) => (
          <TypeAheadParam
            spec={makeSpec({ multiPick: true })}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("Apple")).toBeTruthy();
    expect(screen.getByText("Cherry")).toBeTruthy();
  });
});
