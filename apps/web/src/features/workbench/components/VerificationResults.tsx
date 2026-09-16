import { AlertCircle, Check } from "lucide-react";
import type { ResolvedGene } from "@pathfinder/shared";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface VerificationResultsProps {
  resolvedGenes: ResolvedGene[];
  unresolvedIds: string[];
}

export function VerificationResults({
  resolvedGenes,
  unresolvedIds,
}: VerificationResultsProps) {
  return (
    <div className="mt-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="flex items-center gap-4 text-xs">
        {resolvedGenes.length > 0 && (
          <span className="flex items-center gap-1 text-success">
            <Check className="h-3 w-3" />
            {resolvedGenes.length} valid
          </span>
        )}
        {unresolvedIds.length > 0 && (
          <span className="flex items-center gap-1 text-destructive">
            <AlertCircle className="h-3 w-3" />
            {unresolvedIds.length} not found
          </span>
        )}
      </div>

      {/* Resolved gene details (compact) */}
      {resolvedGenes.length > 0 && (
        <div className="mt-2 max-h-32 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="pb-1 pr-2 font-medium">ID</th>
                <th className="pb-1 pr-2 font-medium">Product</th>
                <th className="pb-1 font-medium">Organism</th>
              </tr>
            </thead>
            <tbody>
              {resolvedGenes.slice(0, 20).map((g) => (
                <tr key={g.geneId} className="text-foreground">
                  <td className="py-0.5 pr-2 font-mono">{g.geneId}</td>
                  <td className="truncate py-0.5 pr-2 max-w-[150px]">
                    {g.product != null && g.product !== "" ? g.product : "-"}
                  </td>
                  <td className="truncate py-0.5 italic max-w-[120px]">
                    {g.organism != null && g.organism !== "" ? g.organism : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {resolvedGenes.length > 20 && (
            <p className="mt-1 text-muted-foreground">
              ... and {resolvedGenes.length - 20} more
            </p>
          )}
        </div>
      )}

      {/* Unresolved IDs */}
      {unresolvedIds.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-medium text-destructive">Not found:</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {unresolvedIds.slice(0, 10).join(", ")}
            {unresolvedIds.length > 10 && ` ... +${unresolvedIds.length - 10} more`}
          </p>
        </div>
      )}
    </div>
  );
}
