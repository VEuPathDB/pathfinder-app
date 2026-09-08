// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { useForm } from "@tanstack/react-form";
import { DateRangeParam } from "./DateRangeParam";
import type { ParamSpec } from "@pathfinder/shared";
import type { ParamWidgetProps } from "./types";
import { WidgetTestForm, getInputByLabel } from "./testUtils";

afterEach(cleanup);

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "dr",
    type: "date-range",
    displayName: "DR",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

describe("DateRangeParam", () => {
  it("renders two date inputs", () => {
    render(
      <WidgetTestForm name="dr" defaultValue="">
        {(field) => (
          <DateRangeParam
            spec={makeSpec()}
            name="dr"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByLabelText(/dr min/i)).toBeTruthy();
    expect(screen.getByLabelText(/dr max/i)).toBeTruthy();
  });

  it("decodes existing 'min:max' value", () => {
    render(
      <WidgetTestForm name="dr" defaultValue="2024-01-01:2024-12-31">
        {(field) => (
          <DateRangeParam
            spec={makeSpec()}
            name="dr"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const min = getInputByLabel("dr min");
    const max = getInputByLabel("dr max");
    expect(min.value).toBe("2024-01-01");
    expect(max.value).toBe("2024-12-31");
  });

  it("encodes range as 'min:max' on change", () => {
    render(
      <WidgetTestForm name="dr" defaultValue="">
        {(field) => (
          <DateRangeParam
            spec={makeSpec()}
            name="dr"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const min = getInputByLabel("dr min");
    const max = getInputByLabel("dr max");
    fireEvent.change(min, { target: { value: "2024-01-01" } });
    fireEvent.change(max, { target: { value: "2024-12-31" } });
    expect(min.value).toBe("2024-01-01");
    expect(max.value).toBe("2024-12-31");
  });

  it("re-renders when field value changes externally (e.g. form.reset)", () => {
    function ExternalDriver({ value }: { value: string }) {
      const form = useForm({
        defaultValues: { dr: value },
        onSubmit: () => {},
      });
      const [prev, setPrev] = useState(value);
      if (value !== prev) {
        setPrev(value);
        form.reset({ dr: value });
      }
      return (
        <form.Field name="dr">
          {(field) => (
            <DateRangeParam
              spec={makeSpec()}
              name="dr"
              options={[]}
              vocabTree={null}
              field={field as unknown as ParamWidgetProps["field"]}
            />
          )}
        </form.Field>
      );
    }

    const { rerender } = render(<ExternalDriver value="2024-01-01:2024-12-31" />);
    expect(getInputByLabel("dr min").value).toBe("2024-01-01");
    expect(getInputByLabel("dr max").value).toBe("2024-12-31");

    rerender(<ExternalDriver value="2025-06-01:2025-06-30" />);
    expect(getInputByLabel("dr min").value).toBe("2025-06-01");
    expect(getInputByLabel("dr max").value).toBe("2025-06-30");
  });
});
