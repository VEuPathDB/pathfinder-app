// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { CheckboxParam } from "./CheckboxParam";
import type { ParamSpec } from "@pathfinder/shared";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

const sampleOptions = [
  { label: "Alpha", value: "a" },
  { label: "Beta", value: "b" },
  { label: "Gamma", value: "c" },
  { label: "Delta", value: "d" },
];

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_param",
    type: "string",
    displayName: "Test",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  } as ParamSpec;
}

describe("CheckboxParam — single-pick (shadcn RadioGroup)", () => {
  it("renders one RadioGroupItem per option", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBe(4);
  });

  it("checks the radio matching the current form value", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="b">
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const beta = screen.getByLabelText("Beta");
    expect(beta.getAttribute("data-state")).toBe("checked");
  });

  it("clicking a radio selects it", async () => {
    const user = userEvent.setup();
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByLabelText("Gamma"));
    expect(screen.getByLabelText("Gamma").getAttribute("data-state")).toBe("checked");
  });
});

describe("CheckboxParam — multi-pick (shadcn Checkbox stack)", () => {
  const spec = makeSpec({ multiPick: true });

  it("renders one Checkbox per option (plus 'Select all' when count > 3)", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getAllByRole("checkbox").length).toBe(5);
  });

  it("does not show 'Select all' when options <= 3", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions.slice(0, 3)}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.queryAllByText(/Select all/)).toHaveLength(0);
  });

  it("toggles a value via the checkbox", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_param" defaultValue={["a"]}>
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByLabelText("Beta"));
    expect(screen.getByLabelText("Beta").getAttribute("data-state")).toBe("checked");
  });

  it("'Select all' selects all options", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByLabelText("Select all"));
    for (const opt of sampleOptions) {
      expect(screen.getByLabelText(opt.label).getAttribute("data-state")).toBe(
        "checked",
      );
    }
  });

  it("'Select all' deselects when all are already selected", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_param" defaultValue={["a", "b", "c", "d"]}>
        {(field) => (
          <CheckboxParam
            spec={spec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByLabelText("Select all"));
    for (const opt of sampleOptions) {
      expect(screen.getByLabelText(opt.label).getAttribute("data-state")).toBe(
        "unchecked",
      );
    }
  });
});
