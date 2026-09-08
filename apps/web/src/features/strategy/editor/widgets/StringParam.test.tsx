// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { StringParam } from "./StringParam";
import type { ParamSpec } from "@pathfinder/shared";
import type { ParamWidgetProps } from "./types";
import { WidgetTestForm, WidgetTestFormWithValidation } from "./testUtils";

afterEach(cleanup);

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

describe("StringParam (form-aware)", () => {
  it("renders a text input by default", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("textbox")).toBeTruthy();
  });

  it("renders with default value from form", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="hello">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const input: HTMLInputElement = screen.getByRole("textbox");
    expect(input.value).toBe("hello");
  });

  it("renders number input for numeric params", () => {
    const spec = makeSpec({ isNumber: true });
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
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

  it("updates form value on change", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "abc" } });
    const input: HTMLInputElement = screen.getByRole("textbox");
    expect(input.value).toBe("abc");
  });

  it("shows validation error for required field on blur", async () => {
    const spec = makeSpec({ allowEmptyValue: false });
    render(
      <WidgetTestFormWithValidation
        name="test_param"
        defaultValue=""
        validator={(v) => (v === "" ? "Required" : undefined)}
      >
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestFormWithValidation>,
    );
    const input = screen.getByRole("textbox");
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
      expect(screen.getByRole("alert").textContent).toBe("Required");
    });
  });

  it("sets aria-invalid when field has error", async () => {
    const spec = makeSpec({ allowEmptyValue: false });
    render(
      <WidgetTestFormWithValidation
        name="test_param"
        defaultValue=""
        validator={(v) => (v === "" ? "Required" : undefined)}
      >
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestFormWithValidation>,
    );
    fireEvent.blur(screen.getByRole("textbox"));
    await waitFor(() => {
      expect(screen.getByRole("textbox").getAttribute("aria-invalid")).toBe("true");
    });
  });

  it("sets aria-required for non-empty params", () => {
    const spec = makeSpec({ allowEmptyValue: false });
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("textbox").getAttribute("aria-required")).toBe("true");
  });

  it("does not set aria-required for optional params", () => {
    const spec = makeSpec({ allowEmptyValue: true });
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("textbox")).not.toHaveAttribute("aria-required");
  });

  it("renders a controlled input when the field value transitions from undefined to a string", () => {
    const spec = makeSpec();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const { rerender } = render(
        <StringParam
          spec={spec}
          name="test_param"
          options={[]}
          vocabTree={null}
          field={
            {
              state: { value: undefined, meta: { errors: [] } },
              handleChange: () => {},
              handleBlur: () => {},
            } as unknown as ParamWidgetProps["field"]
          }
        />,
      );

      rerender(
        <StringParam
          spec={spec}
          name="test_param"
          options={[]}
          vocabTree={null}
          field={
            {
              state: { value: "typed", meta: { errors: [] } },
              handleChange: () => {},
              handleBlur: () => {},
            } as unknown as ParamWidgetProps["field"]
          }
        />,
      );

      const warnings = consoleError.mock.calls
        .map((c) => String(c[0]))
        .filter((m) => m.includes("uncontrolled input to be controlled"));
      expect(warnings).toHaveLength(0);

      const input: HTMLInputElement = screen.getByRole("textbox");
      expect(input.value).toBe("typed");
    } finally {
      consoleError.mockRestore();
    }
  });

  it("renders with min/max/step for numeric params", () => {
    const spec = makeSpec({ isNumber: true, min: 0, max: 100, increment: 5 });
    render(
      <WidgetTestForm name="test_param" defaultValue="">
        {(field) => (
          <StringParam
            spec={spec}
            name="test_param"
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
});
