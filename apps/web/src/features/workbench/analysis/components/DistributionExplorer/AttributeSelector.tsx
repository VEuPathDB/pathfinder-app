import { BarChart3, Loader2, RefreshCw } from "lucide-react";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";

interface AttributeSelectorProps {
  attributes: RecordAttribute[];
  selectedAttr: string;
  onSelect: (attr: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

export function AttributeSelector({
  attributes,
  selectedAttr,
  onSelect,
  onRefresh,
  refreshing,
}: AttributeSelectorProps) {
  return (
    <div className="flex items-center justify-center gap-2">
      <BarChart3 className="h-4 w-4 text-muted-foreground" />
      <select
        value={selectedAttr}
        onChange={(e) => onSelect(e.target.value)}
        className="h-8 rounded-md border border-input bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {attributes.map((attr) => (
          <option key={attr.name} value={attr.name}>
            {attr.displayName}
          </option>
        ))}
      </select>
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        title="Refresh"
      >
        {refreshing ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
}
