// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { useStore } from "@tanstack/react-form";
import type { ParamSpec } from "@pathfinder/shared";
import { useParamForm, type ParamForm } from "../hooks/useParamForm";
import { SelectParam } from "../widgets/SelectParam";
import {
  makeSpec,
  molecularWeightSpecs,
  textSearchSpecs,
  organismOptions,
} from "./fixtures";
import { WidgetTestForm } from "../widgets/testUtils";

afterEach(cleanup);

vi.mock("@/lib/api/sites", () => ({
  refreshDependentParams: vi.fn().mockResolvedValue([]),
}));

function ParamFormWrapper({
  specs,
  onFormReady,
  children,
}: {
  specs: ParamSpec[];
  onFormReady?: (form: ParamForm) => void;
  children?: (form: ParamForm) => React.ReactNode;
}) {
  const { form } = useParamForm(specs);
  if (onFormReady) onFormReady(form);
  return <>{children ? children(form) : null}</>;
}

function FormVal({ form, name }: { form: ParamForm; name: string }) {
  const value = useStore(form.store, (s) => s.values[name]);
  const display = Array.isArray(value) ? JSON.stringify(value) : String(value ?? "");
  return <output data-testid={`fv-${name}`}>{display}</output>;
}

describe("TF: empty param specs", () => {
  it("useParamForm with empty specs produces empty defaults", () => {
    let formRef: ParamForm | null = null;
    render(
      <ParamFormWrapper
        specs={[]}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    expect(formRef!.state.values).toEqual({});
  });
});

describe("TF: all defaults unchanged", () => {
  it("isDirty is false when nothing is changed", () => {
    let formRef: ParamForm | null = null;
    render(
      <ParamFormWrapper
        specs={molecularWeightSpecs()}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    expect(formRef!.state.isDirty).toBe(false);
  });
});

describe("TF: form reset on spec change (search switch)", () => {
  function SpecSwappableForm({
    specs,
    onFormReady,
  }: {
    specs: ParamSpec[];
    onFormReady?: (form: ParamForm) => void;
  }) {
    const { form } = useParamForm(specs);
    if (onFormReady) onFormReady(form);
    return (
      <>
        {specs.map((spec) => (
          <FormVal key={spec.name} form={form} name={spec.name} />
        ))}
      </>
    );
  }

  it("resets form values when specs change (simulating search switch)", () => {
    let formRef: ParamForm | null = null;
    const { rerender } = render(
      <SpecSwappableForm
        specs={molecularWeightSpecs()}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    expect(formRef!.state.values["organism"]).toBe("Plasmodium falciparum 3D7");

    rerender(
      <SpecSwappableForm
        specs={textSearchSpecs()}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    const values = formRef!.state.values;
    expect(values["text_expression"]).toBe("");
    expect(values["text_fields"]).toEqual(["Gene ID", "Product Description"]);
  });
});

describe("TF: hidden and empty-name params are excluded", () => {
  it("hidden params are not included in form defaults", () => {
    const specs = [
      makeSpec({
        name: "visible_param",
        isVisible: true,
        initialDisplayValue: "hello",
      }),
      makeSpec({
        name: "hidden_param",
        isVisible: false,
        initialDisplayValue: "secret",
      }),
    ];
    let formRef: ParamForm | null = null;
    render(
      <ParamFormWrapper
        specs={specs}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    expect(formRef!.state.values["visible_param"]).toBe("hello");
    expect(formRef!.state.values["hidden_param"]).toBeUndefined();
  });
});

describe("TF: select param with required validation", () => {
  it("renders without blank option when allowEmptyValue is false", () => {
    const specs = [
      makeSpec({
        name: "organism",
        displayName: "Organism",
        displayType: "select",
        allowEmptyValue: false,
        initialDisplayValue: "Plasmodium falciparum 3D7",
      }),
    ];
    render(
      <WidgetTestForm name="organism" defaultValue="Plasmodium falciparum 3D7">
        {(field) => (
          <SelectParam
            spec={specs[0]!}
            name="organism"
            options={organismOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(screen.queryByText("-- Select --")).toBeNull();
  });
});
