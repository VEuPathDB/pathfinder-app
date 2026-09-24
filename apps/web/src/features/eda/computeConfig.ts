import { z } from "zod";
import type { EdaDifferentialExpressionConfig } from "@pathfinder/shared/generated/types/EdaDifferentialExpressionConfig";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";
import type { EdaVariableSpec } from "@pathfinder/shared/generated/types/EdaVariableSpec";
import { edaDifferentialExpressionDescriptorSchema } from "@pathfinder/shared/generated/zod/edaDifferentialExpressionDescriptorSchema";

const P_VALUE_FLOOR = "1e-200";
export const GENE_ID_VARIABLE = "VEUPATHDB_GENE_ID";

const NUMERIC_TYPES = ["integer", "number"];
const GROUPED_SHAPES = ["categorical", "ordinal", "binary"];

export type DifferentialExpressionMethod = "DESeq" | "limma";

export interface ComputeConfigDraft {
  identifierEntityId: string;
  identifierVariableId: string;
  valueVariableId: string;
  comparatorEntityId: string;
  comparatorVariableId: string;
  groupA: readonly string[];
  groupB: readonly string[];
  method: DifferentialExpressionMethod;
}

export class DifferentialExpressionConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DifferentialExpressionConfigError";
  }
}

function sharedLabel(draft: ComputeConfigDraft): string | null {
  return draft.groupA.find((label) => draft.groupB.includes(label)) ?? null;
}

/** The rule a complete draft still breaks, or null while it breaks none. */
export function computeConfigProblem(draft: ComputeConfigDraft): string | null {
  const shared = sharedLabel(draft);
  return shared === null ? null : `Group A and group B use the same label: ${shared}`;
}

export function isComputeConfigComplete(draft: ComputeConfigDraft): boolean {
  return (
    draft.identifierEntityId !== "" &&
    draft.identifierVariableId !== "" &&
    draft.valueVariableId !== "" &&
    draft.comparatorEntityId !== "" &&
    draft.comparatorVariableId !== "" &&
    draft.groupA.length > 0 &&
    draft.groupB.length > 0 &&
    sharedLabel(draft) === null
  );
}

export function buildDifferentialExpressionConfig(
  draft: ComputeConfigDraft,
): EdaDifferentialExpressionConfig {
  if (draft.identifierVariableId === "") {
    throw new DifferentialExpressionConfigError(
      `The study declares no ${GENE_ID_VARIABLE} variable`,
    );
  }
  if (draft.valueVariableId === "") {
    throw new DifferentialExpressionConfigError("The value variable is not chosen");
  }
  if (draft.comparatorVariableId === "") {
    throw new DifferentialExpressionConfigError(
      "The comparator variable is not chosen",
    );
  }
  if (draft.groupA.length === 0 || draft.groupB.length === 0) {
    throw new DifferentialExpressionConfigError("Both groups need at least one label");
  }
  const problem = computeConfigProblem(draft);
  if (problem !== null) throw new DifferentialExpressionConfigError(problem);

  return {
    identifierVariable: {
      entityId: draft.identifierEntityId,
      variableId: draft.identifierVariableId,
    },
    valueVariable: {
      entityId: draft.identifierEntityId,
      variableId: draft.valueVariableId,
    },
    comparator: {
      variable: {
        entityId: draft.comparatorEntityId,
        variableId: draft.comparatorVariableId,
      },
      groupA: draft.groupA.map((label) => ({ label })),
      groupB: draft.groupB.map((label) => ({ label })),
    },
    differentialExpressionMethod: draft.method,
    pValueFloor: P_VALUE_FLOOR,
  };
}

/** The computations of an analysis descriptor, each descriptor unread. */
const analysisComputationsSchema = z.object({
  computations: z.array(z.object({ descriptor: z.unknown() })),
});

/** The draft of the comparison the analysis already holds, or null when it
 * holds none. The comparison is the first complete differential expression.
 * The inverse of buildDifferentialExpressionConfig. */
export function computeDraftOf(descriptor: unknown): ComputeConfigDraft | null {
  const parsed = analysisComputationsSchema.safeParse(descriptor);
  const computations = parsed.success ? parsed.data.computations : [];
  const computation = computations
    .map((held) => edaDifferentialExpressionDescriptorSchema.safeParse(held.descriptor))
    .find((read) => read.success)?.data;
  if (computation === undefined) return null;
  const config = computation.configuration;
  return {
    identifierEntityId: config.identifierVariable.entityId,
    identifierVariableId: config.identifierVariable.variableId,
    valueVariableId: config.valueVariable.variableId,
    comparatorEntityId: config.comparator.variable.entityId,
    comparatorVariableId: config.comparator.variable.variableId,
    groupA: config.comparator.groupA.map((range) => range.label),
    groupB: config.comparator.groupB.map((range) => range.label),
    method: config.differentialExpressionMethod ?? "DESeq",
  };
}

function sameLabels(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((label) => b.includes(label));
}

/** Whether two drafts run the same compute. A group is a set of labels. */
export function isSameComputeDraft(
  a: ComputeConfigDraft,
  b: ComputeConfigDraft,
): boolean {
  return (
    a.identifierEntityId === b.identifierEntityId &&
    a.identifierVariableId === b.identifierVariableId &&
    a.valueVariableId === b.valueVariableId &&
    a.comparatorEntityId === b.comparatorEntityId &&
    a.comparatorVariableId === b.comparatorVariableId &&
    a.method === b.method &&
    sameLabels(a.groupA, b.groupA) &&
    sameLabels(a.groupB, b.groupB)
  );
}

/** The gene identifier the export needs. A study declares at most one. */
export function geneIdentifierVariable(
  variables: readonly EdaVariableResponse[],
): EdaVariableSpec | null {
  const found = variables.find((variable) => variable.variableId === GENE_ID_VARIABLE);
  return found === undefined
    ? null
    : { entityId: found.entityId, variableId: found.variableId };
}

/** The plugin reads the value variable from the identifier's own entity. */
export function valueVariables(
  variables: readonly EdaVariableResponse[],
  entityId: string,
): EdaVariableResponse[] {
  return variables.filter(
    (variable) =>
      variable.entityId === entityId && NUMERIC_TYPES.includes(variable.variableType),
  );
}

/** A comparator needs labelled groups, so it needs a vocabulary. */
export function comparatorVariables(
  variables: readonly EdaVariableResponse[],
): EdaVariableResponse[] {
  return variables.filter(
    (variable) =>
      variable.dataShape != null &&
      GROUPED_SHAPES.includes(variable.dataShape) &&
      variable.vocabulary.length > 0,
  );
}
