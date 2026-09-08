// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { NumberParam } from "./NumberParam";
import type { ParamSpec } from "@pathfinder/shared";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "n",
    type: "number",
    displayName: "N",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: true,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("NumberParam", () => {
  it("renders an input of type number", () => {
    render(
      <WidgetTestForm name="n" defaultValue="">
        {(field) => (
          <NumberParam
            spec={makeSpec()}
            name="n"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = screen.getByRole("spinbutton");
    expect(input.getAttribute("type")).toBe("number");
  });

  it("renders min/max/step from spec", () => {
    render(
      <WidgetTestForm name="n" defaultValue="">
        {(field) => (
          <NumberParam
            spec={makeSpec({ min: 0, max: 100, increment: 5 })}
            name="n"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input = screen.getByRole("spinbutton");
    expect(input.getAttribute("min")).toBe("0");
    expect(input.getAttribute("max")).toBe("100");
    expect(input.getAttribute("step")).toBe("5");
  });

  it("updates value on change", () => {
    render(
      <WidgetTestForm name="n" defaultValue="">
        {(field) => (
          <NumberParam
            spec={makeSpec()}
            name="n"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "42" } });
    const input: HTMLInputElement = screen.getByRole("spinbutton");
    expect(input.value).toBe("42");
  });

  it("renders aria-required when allowEmptyValue is false", () => {
    render(
      <WidgetTestForm name="n" defaultValue="">
        {(field) => (
          <NumberParam
            spec={makeSpec({ allowEmptyValue: false })}
            name="n"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("spinbutton").getAttribute("aria-required")).toBe("true");
  });
});
