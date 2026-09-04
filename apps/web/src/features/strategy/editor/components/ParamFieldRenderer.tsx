"use client";

import type { ParamSpec } from "@pathfinder/shared";
import { extractVocabTree, type VocabOption } from "@/lib/utils/vocab";
import { extractSpecVocabulary } from "./stepEditorUtils";
import { resolveWidgetKind } from "../widgets/registry";
import { StringParam } from "../widgets/StringParam";
import { NumberParam } from "../widgets/NumberParam";
import { DateParam } from "../widgets/DateParam";
import { NumberRangeParam } from "../widgets/NumberRangeParam";
import { DateRangeParam } from "../widgets/DateRangeParam";
import { TimestampParam } from "../widgets/TimestampParam";
import { SelectParam } from "../widgets/SelectParam";
import { CheckboxParam } from "../widgets/CheckboxParam";
import { TreeBoxParam } from "../widgets/TreeBoxParam";
import { TypeAheadParam } from "../widgets/TypeAheadParam";
import { FilterParam } from "../widgets/FilterParam";
import { DatasetParam } from "../widgets/DatasetParam";
import type { ParamWidgetProps } from "../widgets/types";
import type { StepEditorState } from "../useStepEditorState";

interface ParamFieldRendererProps {
  spec: ParamSpec;
  state: StepEditorState;
  onFieldChanged: (
    name: string,
    value: unknown,
    allValues: Record<string, unknown>,
  ) => void;
  onFieldBlurred: () => void;
}

export function ParamFieldRenderer({
  spec,
  state,
  onFieldChanged,
  onFieldBlurred,
}: ParamFieldRendererProps) {
  const paramName = spec.name;
  const label = spec.displayName ?? paramName;
  const options =
    state.vocabOptions[paramName] ?? state.dependentOptions[paramName] ?? [];
  const vocabulary = extractSpecVocabulary(spec);
  const vocabTree = extractVocabTree(vocabulary);
  const widgetKind = resolveWidgetKind(spec);

  return (
    <state.form.Field name={paramName}>
      {(field) => {
        const hasFieldError = field.state.meta.errors.length > 0;
        const wrappedField = wrapFieldWithCallbacks(
          field,
          state,
          paramName,
          onFieldChanged,
          onFieldBlurred,
        );

        return (
          <div
            className={
              hasFieldError
                ? "rounded-md border border-destructive/20 bg-destructive/5 p-2"
                : ""
            }
          >
            <label
              htmlFor={paramName}
              className={
                hasFieldError
                  ? "mb-1 block text-xs font-semibold uppercase tracking-wide text-destructive"
                  : "mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              }
            >
              {label}
              {spec.allowEmptyValue === false && (
                <span className="ml-1 text-destructive">*</span>
              )}
            </label>
            <WidgetRenderer
              widgetKind={widgetKind}
              spec={spec}
              name={paramName}
              options={options}
              vocabTree={vocabTree}
              field={wrappedField}
            />
            <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              {state.dependentLoading[paramName] === true && (
                <span>Loading options...</span>
              )}
              {state.dependentErrors[paramName] != null &&
                state.dependentErrors[paramName] !== "" && (
                  <span className="text-destructive">
                    {state.dependentErrors[paramName]}
                  </span>
                )}
            </div>
            {spec.help != null && spec.help !== "" && (
              <p className="mt-1 text-xs text-muted-foreground">{spec.help}</p>
            )}
          </div>
        );
      }}
    </state.form.Field>
  );
}

function wrapFieldWithCallbacks(
  field: ParamWidgetProps["field"],
  state: StepEditorState,
  name: string,
  onFieldChanged: (
    name: string,
    value: unknown,
    allValues: Record<string, unknown>,
  ) => void,
  onFieldBlurred: () => void,
): ParamWidgetProps["field"] {
  return {
    state: field.state,
    handleChange: (value: string | string[]) => {
      field.handleChange(value);
      onFieldChanged(name, value, state.form.state.values);
    },
    handleBlur: () => {
      field.handleBlur();
      onFieldBlurred();
    },
  };
}

interface WidgetRendererProps {
  widgetKind: ReturnType<typeof resolveWidgetKind>;
  spec: ParamSpec;
  name: string;
  options: VocabOption[];
  vocabTree: ParamWidgetProps["vocabTree"];
  field: ParamWidgetProps["field"];
}

function WidgetRenderer({
  widgetKind,
  spec,
  name,
  options,
  vocabTree,
  field,
}: WidgetRendererProps) {
  const widgetProps: ParamWidgetProps = { spec, name, options, vocabTree, field };

  switch (widgetKind) {
    case "treebox":
      return <TreeBoxParam {...widgetProps} />;
    case "typeahead":
      return <TypeAheadParam {...widgetProps} />;
    case "select":
      return <SelectParam {...widgetProps} />;
    case "checkbox":
      return <CheckboxParam {...widgetProps} />;
    case "number":
      return <NumberParam {...widgetProps} />;
    case "date":
      return <DateParam {...widgetProps} />;
    case "number-range":
      return <NumberRangeParam {...widgetProps} />;
    case "date-range":
      return <DateRangeParam {...widgetProps} />;
    case "timestamp":
      return <TimestampParam {...widgetProps} />;
    case "filter":
      return <FilterParam {...widgetProps} />;
    case "dataset":
      return <DatasetParam {...widgetProps} />;
    case "input-step":
      return null;
    case "string":
    default:
      return <StringParam {...widgetProps} />;
  }
}
