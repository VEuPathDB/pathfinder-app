"use client";

import type { ReactNode } from "react";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";

import { Checkbox } from "@/components/ui/checkbox";

import type {
  ComputeConfigDraft,
  DifferentialExpressionMethod,
} from "../computeConfig";

const SELECT_CLASS =
  "h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring";

const METHODS: { value: DifferentialExpressionMethod; label: string }[] = [
  { value: "DESeq", label: "DESeq2" },
  { value: "limma", label: "limma" },
];

export interface ComputeConfigFormProps {
  draft: ComputeConfigDraft;
  values: readonly EdaVariableResponse[];
  comparators: readonly EdaVariableResponse[];
  onChange: (next: ComputeConfigDraft) => void;
}

export function ComputeConfigForm({
  draft,
  values,
  comparators,
  onChange,
}: ComputeConfigFormProps) {
  const comparator =
    comparators.find(
      (variable) => variable.variableId === draft.comparatorVariableId,
    ) ?? null;
  const vocabulary = comparator?.vocabulary ?? [];

  return (
    <div className="grid grid-cols-2 gap-3">
      <Field id="eda-compute-analysis" label="Analysis">
        <select
          id="eda-compute-analysis"
          className={SELECT_CLASS}
          defaultValue="differentialexpression"
        >
          <option value="differentialexpression">Differential expression</option>
        </select>
      </Field>

      <Field id="eda-compute-method" label="Method">
        <select
          id="eda-compute-method"
          className={SELECT_CLASS}
          value={draft.method}
          onChange={(event) =>
            onChange({
              ...draft,
              method: event.target.value === "limma" ? "limma" : "DESeq",
            })
          }
        >
          {METHODS.map((method) => (
            <option key={method.value} value={method.value}>
              {method.label}
            </option>
          ))}
        </select>
      </Field>

      <Field id="eda-compute-value-variable" label="Value variable">
        <select
          id="eda-compute-value-variable"
          className={SELECT_CLASS}
          value={draft.valueVariableId}
          onChange={(event) =>
            onChange({ ...draft, valueVariableId: event.target.value })
          }
        >
          {values.map((variable) => (
            <option key={variable.variableId} value={variable.variableId}>
              {variable.displayName}
            </option>
          ))}
        </select>
      </Field>

      <Field id="eda-compute-comparator" label="Comparator variable">
        <select
          id="eda-compute-comparator"
          className={SELECT_CLASS}
          value={draft.comparatorVariableId}
          onChange={(event) => {
            const chosen =
              comparators.find(
                (variable) => variable.variableId === event.target.value,
              ) ?? null;
            onChange({
              ...draft,
              comparatorEntityId: chosen?.entityId ?? "",
              comparatorVariableId: chosen?.variableId ?? "",
              groupA: [],
              groupB: [],
            });
          }}
        >
          <option value="">Choose a variable...</option>
          {comparators.map((variable) => (
            <option key={variable.variableId} value={variable.variableId}>
              {variable.displayName}
            </option>
          ))}
        </select>
      </Field>

      <GroupField
        label="Reference group (A)"
        checked={draft.groupA}
        taken={draft.groupB}
        vocabulary={vocabulary}
        onChange={(groupA) => onChange({ ...draft, groupA })}
      />
      <GroupField
        label="Comparison group (B)"
        checked={draft.groupB}
        taken={draft.groupA}
        vocabulary={vocabulary}
        onChange={(groupB) => onChange({ ...draft, groupB })}
      />
    </div>
  );
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-[11px] text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

/** One group's labels. A label the other group holds is disabled here, and
 * the checked labels keep the vocabulary's order. */
function GroupField({
  label,
  checked,
  taken,
  vocabulary,
  onChange,
}: {
  label: string;
  checked: readonly string[];
  taken: readonly string[];
  vocabulary: readonly string[];
  onChange: (labels: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(
      vocabulary.filter((entry) =>
        entry === value ? !checked.includes(entry) : checked.includes(entry),
      ),
    );
  return (
    <fieldset className="space-y-1">
      <legend className="text-[11px] text-muted-foreground">{label}</legend>
      <ul className="max-h-40 space-y-1 overflow-y-auto">
        {vocabulary.map((value) => (
          <li key={value} className="flex items-center gap-2">
            <Checkbox
              aria-label={value}
              checked={checked.includes(value)}
              disabled={taken.includes(value)}
              onCheckedChange={() => toggle(value)}
            />
            <span className="text-xs">{value}</span>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
