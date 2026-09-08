import type { ReactNode } from "react";
import { useForm } from "@tanstack/react-form";
import { screen } from "@testing-library/react";
import type { ParamWidgetProps } from "./types";

/** Get an input element by its accessible label. Narrows type to HTMLInputElement. */
export function getInputByLabel(label: string): HTMLInputElement {
  const el = screen.getByLabelText(label);
  if (!(el instanceof HTMLInputElement)) {
    throw new Error(
      `getInputByLabel("${label}"): expected HTMLInputElement, got ${el.tagName}`,
    );
  }
  return el;
}

export function WidgetTestForm({
  name,
  defaultValue,
  children,
}: {
  name: string;
  defaultValue: string | string[];
  children: (field: ParamWidgetProps["field"]) => ReactNode;
}) {
  const form = useForm({
    defaultValues: { [name]: defaultValue },
    onSubmit: () => {},
  });

  return <form.Field name={name}>{(field) => children(field)}</form.Field>;
}

export function WidgetTestFormWithValidation({
  name,
  defaultValue,
  validator,
  children,
}: {
  name: string;
  defaultValue: string | string[];
  validator: (value: string | string[]) => string | undefined;
  children: (field: ParamWidgetProps["field"]) => ReactNode;
}) {
  const form = useForm({
    defaultValues: { [name]: defaultValue },
    onSubmit: () => {},
  });

  return (
    <form.Field
      name={name}
      validators={{
        onBlur: ({ value }: { value: string | string[] }) => validator(value),
      }}
    >
      {(field) => children(field)}
    </form.Field>
  );
}
