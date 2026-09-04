import { Play, Loader2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SweepableParam } from "./types";
import { CategoricalPicker } from "./CategoricalPicker";

interface SweepSetupProps {
  sweepableParams: SweepableParam[];
  selectedParam: SweepableParam | null;
  paramName: string;
  minVal: string;
  maxVal: string;
  steps: string;
  selectedValues: Set<string>;
  loading: boolean;
  error: string | null;
  completedCount: number;
  totalCount: number;
  canRun: boolean;
  formatValue: (v: number | string) => string;
  onMinChange: (v: string) => void;
  onMaxChange: (v: string) => void;
  onStepsChange: (v: string) => void;
  onSelectedValuesChange: (v: Set<string>) => void;
  onParamChange: (name: string) => void;
  onRun: () => void;
  onCancel: () => void;
}

export function SweepSetup({
  sweepableParams,
  selectedParam,
  paramName,
  minVal,
  maxVal,
  steps,
  selectedValues,
  loading,
  error,
  completedCount,
  totalCount,
  canRun,
  formatValue,
  onMinChange,
  onMaxChange,
  onStepsChange,
  onSelectedValuesChange,
  onParamChange,
  onRun,
  onCancel,
}: SweepSetupProps) {
  return (
    <>
      <p className="text-xs text-muted-foreground">
        Sweep a parameter across a range (numeric) or set of values (categorical) to
        visualize the sensitivity/specificity trade-off.
      </p>

      {/* Parameter selector */}
      <div>
        <Label className="mb-1 block text-xs text-muted-foreground">Parameter</Label>
        <select
          value={paramName}
          onChange={(e) => onParamChange(e.target.value)}
          className="h-8 w-full max-w-sm rounded-md border border-input bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Select...</option>
          <optgroup label="Numeric">
            {sweepableParams
              .filter((p) => p.kind === "numeric")
              .map((p) => (
                <option key={p.name} value={p.name}>
                  {p.displayName} (current: {p.currentValue})
                </option>
              ))}
          </optgroup>
          <optgroup label="Categorical">
            {sweepableParams
              .filter((p) => p.kind === "categorical")
              .map((p) => (
                <option key={p.name} value={p.name}>
                  {p.displayName} (current: {formatValue(p.currentValue)})
                </option>
              ))}
          </optgroup>
        </select>
      </div>

      {/* Numeric config */}
      {selectedParam?.kind === "numeric" && (
        <div className="grid grid-cols-3 gap-3">
          <div>
            <Label className="mb-1 block text-xs text-muted-foreground">Min</Label>
            <Input
              type="number"
              value={minVal}
              onChange={(e) => onMinChange(e.target.value)}
              className="h-8 bg-background px-2 text-xs"
            />
          </div>
          <div>
            <Label className="mb-1 block text-xs text-muted-foreground">Max</Label>
            <Input
              type="number"
              value={maxVal}
              onChange={(e) => onMaxChange(e.target.value)}
              className="h-8 bg-background px-2 text-xs"
            />
          </div>
          <div>
            <Label className="mb-1 block text-xs text-muted-foreground">Steps</Label>
            <Input
              type="number"
              min={3}
              max={50}
              value={steps}
              onChange={(e) => onStepsChange(e.target.value)}
              className="h-8 bg-background px-2 text-xs"
            />
          </div>
        </div>
      )}

      {/* Categorical config */}
      {selectedParam?.kind === "categorical" && selectedParam.vocab && (
        <CategoricalPicker
          vocab={selectedParam.vocab}
          selected={selectedValues}
          onChange={onSelectedValuesChange}
        />
      )}

      {/* Run / Cancel */}
      <div className="flex items-center gap-2">
        {loading ? (
          <Button size="sm" variant="destructive" onClick={onCancel}>
            <Square className="h-3.5 w-3.5" />
            Cancel
          </Button>
        ) : (
          <Button size="sm" onClick={onRun} disabled={!canRun}>
            <Play className="h-3.5 w-3.5" />
            Run Sweep
          </Button>
        )}

        {loading && totalCount > 0 && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>
              {completedCount} / {totalCount} points
            </span>
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${(completedCount / totalCount) * 100}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {error != null && <p className="text-xs text-destructive">{error}</p>}
    </>
  );
}
