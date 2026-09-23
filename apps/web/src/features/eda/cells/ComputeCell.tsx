"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EdaComputationDescriptor } from "@pathfinder/shared/generated/types/EdaComputationDescriptor";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { edaStudyDetailOptions } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { useEdaStore } from "@/state/eda";

import {
  buildDifferentialExpressionConfig,
  comparatorVariables,
  computeDraftOf,
  geneIdentifierVariable,
  isComputeConfigComplete,
  isSameComputeDraft,
  valueVariables,
  GENE_ID_VARIABLE,
  type ComputeConfigDraft,
} from "../computeConfig";
import { CellShell } from "./CellShell";
import { ComputeConfigForm } from "./ComputeConfigForm";
import { ComputeProgress } from "./ComputeProgress";

const STUDY_READ_FAILED = "Could not read the study";

export interface ComputeCellProps {
  siteId: string;
  conversationId: string;
  /** The analysis descriptor the thread's route answered, whose compute seeds the form. */
  descriptor?: unknown;
}

export function ComputeCell({ siteId, conversationId, descriptor }: ComputeCellProps) {
  const datasetId = useEdaStore((s) => s.binding?.datasetId ?? "");
  const detail = useQuery({
    ...edaStudyDetailOptions(siteId, datasetId),
    enabled: datasetId !== "",
  });

  const variables = detail.data?.variables ?? [];
  const identifier = geneIdentifierVariable(variables);
  const values =
    identifier === null ? [] : valueVariables(variables, identifier.entityId);
  const comparators = comparatorVariables(variables);

  // The analysis's own compute seeds the form, or an empty draft when it has
  // none. An edit belongs to the seed it was made on, so a new seed wins.
  const recorded = computeDraftOf(descriptor);
  const seed: ComputeConfigDraft | null =
    recorded ??
    (identifier === null
      ? null
      : {
          identifierEntityId: identifier.entityId,
          identifierVariableId: identifier.variableId,
          valueVariableId: values[0]?.variableId ?? "",
          comparatorEntityId: "",
          comparatorVariableId: "",
          groupA: [],
          groupB: [],
          method: "DESeq",
        });
  const seedKey = seed === null ? null : `${datasetId}:${JSON.stringify(seed)}`;
  const [edit, setEdit] = useState<{
    seedKey: string;
    draft: ComputeConfigDraft;
  } | null>(null);
  const draft = edit !== null && edit.seedKey === seedKey ? edit.draft : seed;

  const [submitted, setSubmitted] = useState<EdaComputationDescriptor | null>(null);

  return (
    <CellShell title="Compute" subtitle={null} testId="eda-compute-cell">
      {detail.isPending ? <Spinner className="size-4" /> : null}
      {detail.error != null ? (
        <p data-testid="eda-compute-study-error" className="text-xs text-destructive">
          {toUserMessage(detail.error, STUDY_READ_FAILED)}
        </p>
      ) : null}
      {detail.isSuccess && identifier === null ? (
        <ComputeGeneEntityMissingNotice />
      ) : null}
      {draft !== null && identifier !== null ? (
        <ComputeForm
          conversationId={conversationId}
          draft={draft}
          runnable={
            isComputeConfigComplete(draft) &&
            (recorded === null || !isSameComputeDraft(draft, recorded))
          }
          values={values}
          comparators={comparators}
          submitted={submitted}
          onChange={(next) => {
            if (seedKey !== null) setEdit({ seedKey, draft: next });
          }}
          onRun={() =>
            setSubmitted({
              type: "differentialexpression",
              configuration: buildDifferentialExpressionConfig(draft),
            })
          }
        />
      ) : null}
    </CellShell>
  );
}

function ComputeForm({
  conversationId,
  draft,
  runnable,
  values,
  comparators,
  submitted,
  onChange,
  onRun,
}: {
  conversationId: string;
  draft: ComputeConfigDraft;
  runnable: boolean;
  values: readonly EdaVariableResponse[];
  comparators: readonly EdaVariableResponse[];
  submitted: EdaComputationDescriptor | null;
  onChange: (next: ComputeConfigDraft) => void;
  onRun: () => void;
}) {
  return (
    <div className="space-y-3">
      <ComputeConfigForm
        draft={draft}
        values={values}
        comparators={comparators}
        onChange={onChange}
      />
      <div className="flex justify-end">
        <Button type="button" size="sm" disabled={!runnable} onClick={onRun}>
          Run compute
        </Button>
      </div>
      {submitted !== null ? (
        <ComputeProgress conversationId={conversationId} computation={submitted} />
      ) : null}
    </div>
  );
}

function ComputeGeneEntityMissingNotice() {
  return (
    <p
      data-testid="eda-compute-gene-entity-missing"
      className="text-xs text-muted-foreground"
    >
      {`This study declares no ${GENE_ID_VARIABLE} variable, so it cannot run differential expression.`}
    </p>
  );
}
