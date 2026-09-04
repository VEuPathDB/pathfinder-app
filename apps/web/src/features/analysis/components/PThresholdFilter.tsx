import { Label } from "@/components/ui/label";

interface PThresholdFilterProps {
  value: number;
  onChange: (threshold: number) => void;
}

export function PThresholdFilter({ value, onChange }: PThresholdFilterProps) {
  return (
    <div className="ml-auto flex items-center gap-2 py-2">
      <Label className="text-xs text-muted-foreground">p &le;</Label>
      <select
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label="Filter results by p-value threshold"
        className="rounded border border-border bg-card px-2 py-1 text-xs text-muted-foreground outline-none transition-colors duration-150"
      >
        <option value={0.001}>0.001</option>
        <option value={0.01}>0.01</option>
        <option value={0.05}>0.05</option>
        <option value={0.1}>0.1</option>
        <option value={1}>All</option>
      </select>
    </div>
  );
}
