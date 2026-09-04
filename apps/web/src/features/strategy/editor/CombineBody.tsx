"use client";

import { combineOpEnum } from "@pathfinder/shared";
import type { ColocationParams } from "@pathfinder/shared";
import { VennPicker } from "./components/VennPicker";
import { ColocationEditor, resolveParams } from "./components/ColocationEditor";

interface CombineBodyProps {
  operator: string;
  colocationParams: ColocationParams | null;
  onOperatorChange: (next: string) => void;
  onColocationChange: (next: ColocationParams) => void;
}

export function CombineBody({
  operator,
  colocationParams,
  onOperatorChange,
  onColocationChange,
}: CombineBodyProps) {
  const isColocate = operator === combineOpEnum.COLOCATE;

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Operator
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Click the region you want. The venn is the operator.
        </p>
      </div>
      <VennPicker operator={operator} onChange={onOperatorChange} />
      {isColocate && (
        <ColocationEditor
          initialValues={resolveParams(colocationParams)}
          onChange={onColocationChange}
        />
      )}
    </div>
  );
}
