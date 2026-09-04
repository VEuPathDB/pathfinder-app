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
  computeConfigProblem,
  geneIdentifierVariable,
  isComputeConfigComplete,
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
}

export function ComputeCell({ siteId, conversationId }: ComputeCellProps) {
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

  const [draft, setDraft] = useState<ComputeConfigDraft | null>(null);
  const [seededFor, setSeededFor] = useState<string | null>(null);
  const seedKey = identifier === null ? null : `${datasetId}:${identifier.variableId}`;
  if (identifier !== null && seedKey !== null && seededFor !== seedKey) {
    setSeededFor(seedKey);
    setDraft({
      identifierEntityId: identifier.entityId,
      identifierVariableId: identifier.variableId,
      valueVariableId: values[0]?.variableId ?? "",
      comparatorEntityId: "",
      comparatorVariableId: "",
      groupA: [],
      groupB: [],
      method: "DESeq",
    });
  }

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
          values={values}
          comparators={comparators}
          submitted={submitted}
          onChange={setDraft}
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
  values,
  comparators,
  submitted,
  onChange,
  onRun,
}: {
  conversationId: string;
  draft: ComputeConfigDraft;
  values: readonly EdaVariableResponse[];
  comparators: readonly EdaVariableResponse[];
  submitted: EdaComputationDescriptor | null;
  onChange: (next: ComputeConfigDraft) => void;
  onRun: () => void;
}) {
  const problem = computeConfigProblem(draft);
  return (
    <div className="space-y-3">
      <ComputeConfigForm
        draft={draft}
        values={values}
        comparators={comparators}
        onChange={onChange}
      />
      {problem !== null ? (
        <p data-testid="eda-compute-config-error" className="text-xs text-destructive">
          {problem}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          disabled={!isComputeConfigComplete(draft)}
          onClick={onRun}
        >
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
