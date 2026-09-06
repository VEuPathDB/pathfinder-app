import { Loader2, X } from "lucide-react";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import { AttributeValueRich } from "./ResultsTableColumns";

interface ExpandedRowDetailProps {
  pk: string;
  detail: RecordDetailResponse | null;
  error: string | null;
  loading: boolean;
  onClose: () => void;
}

export function ExpandedRowDetail({
  pk,
  detail,
  error,
  loading,
  onClose,
}: ExpandedRowDetailProps) {
  const attrs = detail?.attributes;
  const nameMap = detail?.attributeNames;
  const entries = attrs ? Object.entries(attrs) : [];
  const hasContent = entries.length > 0;

  return (
    <div className="border-t border-border bg-muted/30 px-6 py-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Record Detail — {pk}
        </h4>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading details...
        </div>
      ) : error != null ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      ) : hasContent ? (
        <div className="max-h-72 overflow-y-auto">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm">
            {entries.map(([key, val]) => (
              <div key={key} className="contents">
                <dt className="whitespace-nowrap font-medium text-muted-foreground">
                  {nameMap?.[key] ?? key}
                </dt>
                <dd className="text-foreground">
                  <AttributeValueRich value={val} />
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <p className="py-4 text-sm text-muted-foreground">Unable to load details.</p>
      )}
    </div>
  );
}
