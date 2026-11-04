"use client";

import { useId } from "react";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { ConfirmationEvidence } from "@pathfinder/shared/generated/types/ConfirmationEvidence";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { Fact } from "@pathfinder/shared/generated/types/Fact";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { BreakStrip } from "./BreakStrip";
import { GeneModelFigure } from "./GeneModelFigure";
import { drawableModels } from "./geneModelTracks";
import { LocusFigure } from "./LocusFigure";
import { ProteinFigure } from "./ProteinFigure";
import { confirmationTracks, findingTracks, tracksTitle } from "./proteinTracks";
import { RelativesPlot } from "./RelativesPlot";
import { relativesOutcome } from "./relativesPoints";
import { EvidenceRegion } from "./RelativesSection";

function ConfirmationFigures({
  detail,
  confirmation,
  words,
}: {
  detail: FindingDetail;
  confirmation: ConfirmationEvidence["confirmation"];
  words: AuditWords;
}) {
  return (
    <>
      {drawableModels(detail.models) === null ? (
        <ProteinFigure
          title={tracksTitle(confirmation.check === "pseudogene_call")}
          tracks={confirmationTracks(confirmation)}
        />
      ) : null}
      <BreakStrip confirmation={confirmation} />
      {confirmation.check === "missing_gene" ? (
        <LocusFigure audit={confirmation.result} />
      ) : null}
      {confirmation.check === "strain_model" ? (
        <RelativesPlot outcome={relativesOutcome(detail, words)} />
      ) : null}
    </>
  );
}

export function ConfirmationSection({
  detail,
  evidence,
  facts,
  words,
}: {
  detail: FindingDetail;
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
}) {
  const { payload } = evidence;
  return (
    <EvidenceRegion
      evidence={evidence}
      facts={facts}
      words={words}
      lead={detail.finding.verdictText}
      figures={
        payload?.kind === "confirmation" ? (
          <ConfirmationFigures
            detail={detail}
            confirmation={payload.confirmation}
            words={words}
          />
        ) : null
      }
    />
  );
}

export function GeneModelsSection({ detail }: { detail: FindingDetail }) {
  const headingId = useId();
  const models = drawableModels(detail.models);
  return (
    <section aria-labelledby={headingId} className="mt-6 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Gene models
      </h2>
      {models === null ? (
        <p className="mt-1">No gene model stored for this finding</p>
      ) : (
        <GeneModelFigure models={models} proteinTracks={findingTracks(detail)} />
      )}
    </section>
  );
}
