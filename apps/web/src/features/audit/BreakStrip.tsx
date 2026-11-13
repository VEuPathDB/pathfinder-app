import type { ConfirmationEvidence } from "@strategist/shared/generated/types/ConfirmationEvidence";
import type { PseudogeneCallAudit } from "@strategist/shared/generated/types/PseudogeneCallAudit";
import type { SelenoproteinEndAudit } from "@strategist/shared/generated/types/SelenoproteinEndAudit";

import { joinWords } from "./format";

const RESIDUE_WORDS: Record<string, string> = { "*": "stop", U: "selenocysteine" };

function residueWord(residue: string): string {
  return RESIDUE_WORDS[residue] ?? residue;
}

function ResidueRows({ audit }: { audit: SelenoproteinEndAudit }) {
  const rows = [
    { label: "Genome after the model's end", residues: [...audit.afterModelEnd] },
    { label: "Reference from its selenocysteine", residues: [...audit.referenceTail] },
  ].filter((row) => row.residues.length > 0);
  if (rows.length === 0) return null;
  const spoken = rows
    .map((row) => `${row.label}: ${row.residues.map(residueWord).join(", ")}.`)
    .join(" ");
  return (
    <div role="img" aria-label={spoken} className="mt-3 space-y-1 text-xs">
      {rows.map((row) => (
        <div key={row.label} className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">{row.label}</span>
          <span className="flex flex-wrap font-mono">
            {row.residues.map((residue, index) => (
              <span
                key={`${String(index)}-${residue}`}
                data-part="residue"
                className="w-5 border border-border text-center"
              >
                {residue}
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

function StopsLine({ audit }: { audit: PseudogeneCallAudit }) {
  const stops = audit.prematureStops;
  if (stops.length === 0) return null;
  const word = stops.length === 1 ? "residue" : "residues";
  const listed = joinWords(stops.map((stop) => stop.toLocaleString("en-US")));
  const cut =
    audit.prematureStopsTruncated === true
      ? ` (the first ${String(stops.length)})`
      : "";
  return (
    <p className="mt-3 text-xs">{`Stops inside the rebuilt protein at ${word} ${listed}${cut}`}</p>
  );
}

export function BreakStrip({
  confirmation,
}: {
  confirmation: ConfirmationEvidence["confirmation"];
}) {
  switch (confirmation.check) {
    case "selenoprotein_end":
      return <ResidueRows audit={confirmation.result} />;
    case "pseudogene_call":
      return <StopsLine audit={confirmation.result} />;
    case "gene_fusion":
    case "gene_length":
    case "gene_split":
    case "intron_support":
    case "missing_gene":
    case "organelle_join":
    case "strain_model":
      return null;
  }
}
