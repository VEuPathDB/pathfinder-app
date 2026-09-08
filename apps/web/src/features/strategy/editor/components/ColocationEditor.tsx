"use client";

import { useStore } from "@tanstack/react-form";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { ColocationFormValues } from "../schema/colocationSchema";
import { useColocationForm, type ColocationForm } from "../hooks/useColocationForm";

export const DEFAULT_COLOCATION: ColocationFormValues = {
  operation: "overlaps",
  strand: "either strand",
  output: "a",
  regionA: "exact",
  beginA: "start",
  beginDirectionA: "+",
  beginOffsetA: 0,
  endA: "stop",
  endDirectionA: "+",
  endOffsetA: 0,
  regionB: "exact",
  beginB: "start",
  beginDirectionB: "+",
  beginOffsetB: 0,
  endB: "stop",
  endDirectionB: "+",
  endOffsetB: 0,
};

export function resolveParams(
  params: Partial<ColocationFormValues> | null | undefined,
): ColocationFormValues {
  return { ...DEFAULT_COLOCATION, ...params };
}

function ColocationChangeSync({
  form,
  onChange,
}: {
  form: ColocationForm;
  onChange: (values: ColocationFormValues) => void;
}) {
  const values = useStore(form.store, (s) => s.values);
  queueMicrotask(() => onChange(values));
  return null;
}

interface ToggleOption<T extends string> {
  value: T;
  label: string;
}

function ToggleRow<T extends string>({
  options,
  value,
  onChange,
}: {
  options: ToggleOption<T>[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      variant="outline"
      size="sm"
      onValueChange={(v) => {
        if (v !== "" && v !== value) onChange(v as T);
      }}
    >
      {options.map((opt) => (
        <ToggleGroupItem key={opt.value} value={opt.value} aria-label={opt.label}>
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

function OffsetRow({
  label,
  anchorField,
  directionField,
  offsetField,
  form,
}: {
  label: string;
  anchorField: keyof ColocationFormValues;
  directionField: keyof ColocationFormValues;
  offsetField: keyof ColocationFormValues;
  form: ColocationForm;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="flex items-center gap-1">
        <form.Field name={anchorField}>
          {(field) => (
            <ToggleRow
              options={[
                { value: "start", label: "Start" },
                { value: "stop", label: "Stop" },
              ]}
              value={field.state.value as "start" | "stop"}
              onChange={(v) => field.handleChange(v)}
            />
          )}
        </form.Field>
        <form.Field name={directionField}>
          {(field) => (
            <ToggleRow
              options={[
                { value: "+", label: "+" },
                { value: "-", label: "−" },
              ]}
              value={field.state.value as "+" | "-"}
              onChange={(v) => field.handleChange(v)}
            />
          )}
        </form.Field>
        <form.Field name={offsetField}>
          {(field) => (
            <Input
              type="number"
              min={0}
              value={typeof field.state.value === "number" ? field.state.value : 0}
              onChange={(event) =>
                field.handleChange(Math.max(0, Number(event.target.value || 0)))
              }
              onBlur={field.handleBlur}
              className="h-8 w-20 text-xs"
            />
          )}
        </form.Field>
      </div>
    </div>
  );
}

function RegionEditor({
  label,
  suffix,
  form,
}: {
  label: string;
  suffix: "A" | "B";
  form: ColocationForm;
}) {
  const regionKey = `region${suffix}` as keyof ColocationFormValues;
  const beginKey = `begin${suffix}` as keyof ColocationFormValues;
  const beginDirKey = `beginDirection${suffix}` as keyof ColocationFormValues;
  const beginOffKey = `beginOffset${suffix}` as keyof ColocationFormValues;
  const endKey = `end${suffix}` as keyof ColocationFormValues;
  const endDirKey = `endDirection${suffix}` as keyof ColocationFormValues;
  const endOffKey = `endOffset${suffix}` as keyof ColocationFormValues;

  const region = useStore(form.store, (s) => s.values[regionKey]);
  const showDetails = region !== "exact";

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <form.Field name={regionKey}>
        {(field) => (
          <ToggleRow
            options={[
              { value: "exact", label: "Exact" },
              { value: "upstream", label: "Upstream" },
              { value: "downstream", label: "Downstream" },
              { value: "custom", label: "Custom" },
            ]}
            value={field.state.value as "exact" | "upstream" | "downstream" | "custom"}
            onChange={(r) => {
              field.handleChange(r);
              if (r === "exact") {
                form.setFieldValue(beginKey, "start");
                form.setFieldValue(beginDirKey, "+");
                form.setFieldValue(beginOffKey, 0);
                form.setFieldValue(endKey, "stop");
                form.setFieldValue(endDirKey, "+");
                form.setFieldValue(endOffKey, 0);
              } else if (r === "upstream") {
                form.setFieldValue(beginKey, "start");
                form.setFieldValue(beginDirKey, "-");
                form.setFieldValue(beginOffKey, 0);
                form.setFieldValue(endKey, "start");
                form.setFieldValue(endDirKey, "+");
                form.setFieldValue(endOffKey, 0);
              } else if (r === "downstream") {
                form.setFieldValue(beginKey, "stop");
                form.setFieldValue(beginDirKey, "-");
                form.setFieldValue(beginOffKey, 0);
                form.setFieldValue(endKey, "stop");
                form.setFieldValue(endDirKey, "+");
                form.setFieldValue(endOffKey, 0);
              }
            }}
          />
        )}
      </form.Field>
      {showDetails && (
        <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-background p-2">
          <OffsetRow
            label="Begin"
            anchorField={beginKey}
            directionField={beginDirKey}
            offsetField={beginOffKey}
            form={form}
          />
          <OffsetRow
            label="End"
            anchorField={endKey}
            directionField={endDirKey}
            offsetField={endOffKey}
            form={form}
          />
        </div>
      )}
    </div>
  );
}

export function ColocationEditor({
  initialValues,
  onChange,
}: {
  initialValues?: Partial<ColocationFormValues>;
  onChange?: (values: ColocationFormValues) => void;
}) {
  const form = useColocationForm(initialValues);

  return (
    <>
      {onChange != null && <ColocationChangeSync form={form} onChange={onChange} />}
      <Card className="mt-3 space-y-3 rounded-md p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Colocation parameters
        </div>

        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Operation</div>
          <form.Field name="operation">
            {(field) => (
              <ToggleRow
                options={[
                  { value: "overlaps", label: "Overlaps" },
                  { value: "contains", label: "Contains" },
                  { value: "is contained in", label: "Is contained in" },
                ]}
                value={field.state.value}
                onChange={(v) => field.handleChange(v)}
              />
            )}
          </form.Field>
        </div>

        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Strand</div>
          <form.Field name="strand">
            {(field) => (
              <ToggleRow
                options={[
                  { value: "either strand", label: "Either" },
                  { value: "same strand", label: "Same" },
                  { value: "opposite strand", label: "Opposite" },
                ]}
                value={field.state.value}
                onChange={(v) => field.handleChange(v)}
              />
            )}
          </form.Field>
        </div>

        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Output</div>
          <form.Field name="output">
            {(field) => (
              <ToggleRow
                options={[
                  { value: "a", label: "Step A" },
                  { value: "b", label: "Step B" },
                ]}
                value={field.state.value}
                onChange={(v) => field.handleChange(v)}
              />
            )}
          </form.Field>
        </div>

        <RegionEditor label="Region A" suffix="A" form={form} />
        <RegionEditor label="Region B" suffix="B" form={form} />
      </Card>
    </>
  );
}
