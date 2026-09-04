import type { ScoredComparison, ScoredVariant } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

function fmt(value: number | null | undefined): string {
  return value == null ? "-" : value.toFixed(2);
}

function hasFailed(variant: ScoredVariant): boolean {
  return variant.error != null && variant.error !== "";
}

function membership(variant: ScoredVariant): string {
  const hits = variant.controlHits ?? [];
  return hits.length === 0
    ? "contains none of the control genes"
    : `contains ${hits.join(", ")}`;
}

function caption(data: ScoredComparison): string {
  const count = `${data.variants.length.toLocaleString()} variants`;
  const winner = data.variants.find((v) => v.label === data.winnerLabel);
  if (data.winnerLabel != null && winner !== undefined) {
    return `${count}, winner ${data.winnerLabel} at ${fmt(winner.mcc)}`;
  }
  const failed = data.variants.filter(hasFailed).length;
  if (failed > 0) {
    return `scoring failed for ${failed.toLocaleString()} of ${count}`;
  }
  return `${count}, no winner`;
}

export function DataScoredComparison({ data }: { data: ScoredComparison }) {
  return (
    <Figure
      testId="data-scored-comparison"
      title="Scored variants"
      caption={caption(data)}
    >
      <div className="text-xs">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
          ranked by {data.objective}
        </p>

        <ul className="mt-2 space-y-1.5">
          {data.variants.map((v) => {
            const isWinner = data.winnerLabel != null && v.label === data.winnerLabel;
            const failed = hasFailed(v);
            return (
              <li key={v.label}>
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-foreground">{v.label}</span>
                  {isWinner ? (
                    <span className="text-[10px] font-medium text-primary">winner</span>
                  ) : null}
                  <span className="ml-auto font-mono text-[11px] text-foreground">
                    {failed ? "-" : `MCC ${fmt(v.mcc)}`}
                  </span>
                </div>
                {failed ? (
                  <div className="mt-0.5 text-[11px] text-destructive">
                    scoring failed: {v.error}
                  </div>
                ) : (
                  <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {`F1 ${fmt(v.f1)}, prec ${fmt(v.precision)}, sens ${fmt(v.sensitivity)}, bal-acc ${fmt(v.balancedAccuracy)}`}
                  </div>
                )}
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {membership(v)}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </Figure>
  );
}
