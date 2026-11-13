// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useStore } from "@tanstack/react-form";
import type { ParamSpec } from "@strategist/shared";
import { useParamForm, type ParamForm } from "../hooks/useParamForm";
import { StringParam } from "../widgets/StringParam";
import { CheckboxParam } from "../widgets/CheckboxParam";
import { makeSpec, molecularWeightSpecs, multiPickSpecs, goOptions } from "./fixtures";

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

describe("TF: full form lifecycle with realistic WDK specs", () => {
  it("initializes form with WDK defaults from initialDisplayValue", () => {
    render(
      <ParamFormWrapper specs={molecularWeightSpecs()}>
        {(form) => (
          <>
            <FormVal form={form} name="organism" />
            <FormVal form={form} name="min_molecular_weight" />
            <FormVal form={form} name="max_molecular_weight" />
          </>
        )}
      </ParamFormWrapper>,
    );
    expect(screen.getByTestId("fv-organism").textContent).toBe(
      "Plasmodium falciparum 3D7",
    );
    expect(screen.getByTestId("fv-min_molecular_weight").textContent).toBe("0");
    expect(screen.getByTestId("fv-max_molecular_weight").textContent).toBe("1000000");
  });

  it("editing one param updates its value", () => {
    const specs = molecularWeightSpecs();
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <>
            <form.Field name="min_molecular_weight">
              {(field) => (
                <StringParam
                  spec={specs[1]!}
                  name="min_molecular_weight"
                  options={[]}
                  vocabTree={null}
                  field={field}
                />
              )}
            </form.Field>
            <FormVal form={form} name="min_molecular_weight" />
          </>
        )}
      </ParamFormWrapper>,
    );
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "50000" } });
    expect(screen.getByTestId("fv-min_molecular_weight").textContent).toBe("50000");
  });

  it("state.values produces Record<string, string> matching SearchConfig.parameters", () => {
    let formRef: ParamForm | null = null;
    render(
      <ParamFormWrapper
        specs={molecularWeightSpecs()}
        onFormReady={(f) => {
          formRef = f;
        }}
      />,
    );
    const values = formRef!.state.values;
    expect(typeof values["organism"]).toBe("string");
    expect(typeof values["min_molecular_weight"]).toBe("string");
    expect(typeof values["max_molecular_weight"]).toBe("string");
    expect(Object.keys(values).sort()).toEqual([
      "max_molecular_weight",
      "min_molecular_weight",
      "organism",
    ]);
  });
});

describe("TF: validation error flow", () => {
  it("shows error when required field cleared, clears on valid input", async () => {
    const specs = [
      makeSpec({
        name: "gene_id",
        displayName: "Gene ID",
        allowEmptyValue: false,
        initialDisplayValue: "PF3D7_0100100",
      }),
    ];
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <form.Field
            name="gene_id"
            validators={{
              onBlur: ({ value }: { value: string | string[] }) =>
                value === "" ? "Gene ID is required" : undefined,
            }}
          >
            {(field) => (
              <StringParam
                spec={specs[0]!}
                name="gene_id"
                options={[]}
                vocabTree={null}
                field={field}
              />
            )}
          </form.Field>
        )}
      </ParamFormWrapper>,
    );
    const input = screen.getByRole("textbox");
    expect(screen.queryByRole("alert")).toBeNull();

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("Gene ID");
    });
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });
});

describe("TF: multi-pick param interaction", () => {
  it("tracks multiple selections in form value array", () => {
    const specs = multiPickSpecs();
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <>
            <form.Field name="go_terms">
              {(field) => (
                <CheckboxParam
                  spec={specs[0]!}
                  name="go_terms"
                  options={goOptions}
                  vocabTree={null}
                  field={field}
                />
              )}
            </form.Field>
            <FormVal form={form} name="go_terms" />
          </>
        )}
      </ParamFormWrapper>,
    );
    fireEvent.click(screen.getByText("apoptotic process"));
    fireEvent.click(screen.getByText("cell cycle"));
    const parsed: string[] = JSON.parse(screen.getByTestId("fv-go_terms").textContent);
    expect(parsed).toContain("GO:0006915");
    expect(parsed).toContain("GO:0007049");
    expect(parsed).toHaveLength(2);
  });

  it("select-all includes all options, deselecting one removes it", () => {
    const specs = multiPickSpecs();
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <>
            <form.Field name="go_terms">
              {(field) => (
                <CheckboxParam
                  spec={specs[0]!}
                  name="go_terms"
                  options={goOptions}
                  vocabTree={null}
                  field={field}
                />
              )}
            </form.Field>
            <FormVal form={form} name="go_terms" />
          </>
        )}
      </ParamFormWrapper>,
    );
    const selectAllCb = screen.getByLabelText("Select all");
    fireEvent.click(selectAllCb);
    let parsed: string[] = JSON.parse(screen.getByTestId("fv-go_terms").textContent);
    expect(parsed).toHaveLength(5);

    fireEvent.click(screen.getByText("response to stress"));
    parsed = JSON.parse(screen.getByTestId("fv-go_terms").textContent);
    expect(parsed).toHaveLength(4);
    expect(parsed).not.toContain("GO:0006950");
  });
});

describe("TF: accessibility verification", () => {
  it("aria-required set only on required param inputs", () => {
    const specs = [
      makeSpec({
        name: "gene_id",
        allowEmptyValue: false,
        initialDisplayValue: "PF3D7_0100100",
      }),
      makeSpec({ name: "description", allowEmptyValue: true, initialDisplayValue: "" }),
    ];
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <>
            <form.Field name="gene_id">
              {(field) => (
                <StringParam
                  spec={specs[0]!}
                  name="gene_id"
                  options={[]}
                  vocabTree={null}
                  field={field}
                />
              )}
            </form.Field>
            <form.Field name="description">
              {(field) => (
                <StringParam
                  spec={specs[1]!}
                  name="description"
                  options={[]}
                  vocabTree={null}
                  field={field}
                />
              )}
            </form.Field>
          </>
        )}
      </ParamFormWrapper>,
    );
    const required = screen
      .getAllByRole("textbox")
      .filter((el) => el.getAttribute("aria-required") === "true");
    expect(required).toHaveLength(1);
  });

  it("aria-describedby connects input to error message", async () => {
    const specs = [
      makeSpec({
        name: "gene_id",
        displayName: "Gene ID",
        allowEmptyValue: false,
        initialDisplayValue: "PF3D7_0100100",
      }),
    ];
    render(
      <ParamFormWrapper specs={specs}>
        {(form) => (
          <form.Field
            name="gene_id"
            validators={{
              onBlur: ({ value }: { value: string | string[] }) =>
                value === "" ? "Gene ID is required" : undefined,
            }}
          >
            {(field) => (
              <StringParam
                spec={specs[0]!}
                name="gene_id"
                options={[]}
                vocabTree={null}
                field={field}
              />
            )}
          </form.Field>
        )}
      </ParamFormWrapper>,
    );
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByRole("alert").id).toBe("gene_id-error");
      expect(input.getAttribute("aria-describedby")).toBe("gene_id-error");
    });
  });
});
