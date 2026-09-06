import { Loader2 } from "lucide-react";
import { Modal } from "@/lib/components/Modal";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import type { DistributionEntry } from "./types";

// --- Bar list ---

interface BarListProps {
  entries: DistributionEntry[];
  maxCount: number;
  totalCount: number;
  onBarClick: (value: string) => void;
}

function BarList({ entries, maxCount, totalCount, onBarClick }: BarListProps) {
  const topEntries = entries.slice(0, 20);

  if (topEntries.length === 0) {
    return (
      <div className="py-6 text-center text-xs text-muted-foreground">
        No distribution data available for this attribute.
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {topEntries.map(({ value, count }) => {
        const pct = (count / maxCount) * 100;
        return (
          <div
            key={value}
            className="group flex cursor-pointer items-center gap-3"
            onClick={() => onBarClick(value)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onBarClick(value);
              }
            }}
          >
            <span
              className="w-28 shrink-0 truncate text-right text-xs text-muted-foreground"
              title={value}
            >
              {value || "(empty)"}
            </span>
            <div className="relative h-5 flex-1 overflow-hidden rounded bg-muted/40">
              <div
                className="absolute inset-y-0 left-0 rounded bg-primary/20 transition-all duration-300 group-hover:bg-primary/30"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-xs tabular-nums text-foreground">
              {count.toLocaleString()}
            </span>
          </div>
        );
      })}
      {totalCount > 20 && (
        <p className="pt-1 text-right text-xs text-muted-foreground">
          Showing top 20 of {totalCount} values
        </p>
      )}
    </div>
  );
}

// --- Drill-down modal ---

interface DrillDownModalProps {
  modalValue: string | null;
  onClose: () => void;
  selectedAttr: string;
  attributes: RecordAttribute[];
  records: ClassifiedRecord[];
  loading: boolean;
}

function DrillDownModal({
  modalValue,
  onClose,
  selectedAttr,
  attributes,
  records,
  loading,
}: DrillDownModalProps) {
  const displayName =
    attributes.find((a) => a.name === selectedAttr)?.displayName ?? selectedAttr;
  const hasClassifications = records.some((r) => r.classification != null);

  return (
    <Modal
      open={modalValue !== null}
      onClose={onClose}
      title={`Genes: ${selectedAttr} = ${modalValue}`}
      maxWidth="max-w-2xl"
      showCloseButton
    >
      <div className="p-4">
        <h3 className="mb-3 text-sm font-medium text-foreground">
          {displayName} = &ldquo;{modalValue}&rdquo;
        </h3>

        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading genes...
          </div>
        ) : records.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No matching genes found.
          </p>
        ) : (
          <div className="max-h-80 overflow-auto rounded border border-border">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted text-left">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Gene ID</th>
                  <th className="px-3 py-1.5 font-medium">Product</th>
                  {hasClassifications && (
                    <th className="px-3 py-1.5 font-medium">Class</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {records.map((rec) => {
                  const rawId =
                    rec.id.find((k) => k.name === "gene_source_id")?.value ??
                    rec.id[0]?.value ??
                    "\u2014";
                  return (
                    <tr key={rawId} className="hover:bg-muted/40">
                      <td className="px-3 py-1.5 font-mono">{rawId}</td>
                      <td
                        className="max-w-xs truncate px-3 py-1.5"
                        title={String(rec.attributes["gene_product"] ?? "")}
                      >
                        {String(rec.attributes["gene_product"] ?? "\u2014")}
                      </td>
                      {hasClassifications && (
                        <td className="px-3 py-1.5">
                          {rec.classification ?? "\u2014"}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!loading && records.length > 0 && (
          <p className="mt-2 text-right text-xs text-muted-foreground">
            {records.length} gene{records.length !== 1 && "s"}
          </p>
        )}
      </div>
    </Modal>
  );
}

// --- Main chart component ---

interface DistributionChartProps {
  distribution: DistributionEntry[];
  loading: boolean;
  selectedAttr: string;
  attributes: RecordAttribute[];
  modalValue: string | null;
  modalRecords: ClassifiedRecord[];
  loadingModal: boolean;
  onBarClick: (value: string) => void;
  onCloseModal: () => void;
}

export function DistributionChart({
  distribution,
  loading,
  selectedAttr,
  attributes,
  modalValue,
  modalRecords,
  loadingModal,
  onBarClick,
  onCloseModal,
}: DistributionChartProps) {
  const maxCount = Math.max(1, ...distribution.map((d) => d.count));

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading distribution...
      </div>
    );
  }

  return (
    <>
      <BarList
        entries={distribution}
        maxCount={maxCount}
        totalCount={distribution.length}
        onBarClick={onBarClick}
      />
      <DrillDownModal
        modalValue={modalValue}
        onClose={onCloseModal}
        selectedAttr={selectedAttr}
        attributes={attributes}
        records={modalRecords}
        loading={loadingModal}
      />
    </>
  );
}
