// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { SelectParam } from "./SelectParam";
import type { ParamSpec } from "@pathfinder/shared";
import type { VocabOption } from "@/lib/utils/vocab";
import { WidgetTestForm, WidgetTestFormWithValidation } from "./testUtils";

afterEach(cleanup);

const sampleOptions: VocabOption[] = [
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
  };
}

describe("SelectParam (single-pick, shadcn Select)", () => {
  it("renders a shadcn Select trigger as combobox", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <SelectParam
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

  it("displays the placeholder when value is empty", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <SelectParam
            spec={makeSpec()}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("-- Select --")).toBeTruthy();
  });

  it("opens and lists options on click", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <SelectParam
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
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.getByText("Beta")).toBeTruthy();
  });

  it("sets aria-invalid when field has error", async () => {
    render(
      <WidgetTestFormWithValidation
        name="test_param"
        defaultValue=""
        validator={(v) => (v === "" ? "Required" : undefined)}
      >
        {(field) => (
          <SelectParam
            spec={makeSpec({ allowEmptyValue: false })}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestFormWithValidation>,
    );
    fireEvent.blur(screen.getByRole("combobox"));
    // Allow time for validation
    await new Promise((r) => setTimeout(r, 30));
    const select = screen.getByRole("combobox");
    expect(select.getAttribute("aria-invalid")).toBe("true");
  });
});

describe("SelectParam (multi-pick, shadcn Checkbox stack)", () => {
  const multiSpec = makeSpec({ multiPick: true });

  it("renders one shadcn Checkbox per option", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <SelectParam
            spec={multiSpec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const checkboxes = screen.getAllByRole("checkbox");
    // 4 options + 1 select-all when count > 3
    expect(checkboxes.length).toBe(5);
  });

  it("shows 'Select all' toggle when options > 3", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <SelectParam
            spec={multiSpec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText(/Select all/)).toBeTruthy();
  });

  it("does not show 'Select all' when options <= 3", () => {
    render(
      <WidgetTestForm name="test_param" defaultValue={[]}>
        {(field) => (
          <SelectParam
            spec={multiSpec}
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
          <SelectParam
            spec={multiSpec}
            name="test_param"
            options={sampleOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByLabelText("Beta"));
    // After clicking Beta we expect data-state on the Beta checkbox to flip
    const beta = screen.getByLabelText("Beta");
    expect(beta.getAttribute("data-state")).toBe("checked");
  });
});
