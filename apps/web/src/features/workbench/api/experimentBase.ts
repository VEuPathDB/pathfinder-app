import type { GeneSet } from "@pathfinder/shared";
import type { CreateExperimentRequest } from "@pathfinder/shared/generated/types/CreateExperimentRequest";

import { CONTROLS_PARAM_NAME, CONTROLS_SEARCH_NAME } from "../constants";

type SetParameters = NonNullable<GeneSet["parameters"]>;

/** What a saved set gives an experiment to run. */
export type ExperimentBasis =
  | { kind: "search"; searchName: string; parameters: SetParameters }
  | { kind: "geneList"; geneIds: string[] }
  | { kind: "none" };

/** WDK names a combine step this way. A combine runs no search of its own. */
const COMBINE_STEP_PREFIX = "boolean_question_";

const NOTHING_TO_RUN =
  "This set holds no genes and records no search, so there is nothing to run.";

/** The search a set records, or null when what it records is not one. */
function recordedSearch(geneSet: GeneSet): string | null {
  const searchName = geneSet.searchName ?? "";
  if (searchName === "" || searchName.startsWith(COMBINE_STEP_PREFIX)) return null;
  return searchName;
}

/** The parameters a set records, or null when none can be trusted to re-run it.
 *
 * An empty map is not a promise that the step set none: a search document whose
 * values the decoder does not know gives the same empty map.
 */
function recordedParameters(geneSet: GeneSet): SetParameters | null {
  const parameters = geneSet.parameters;
  if (parameters == null || Object.keys(parameters).length === 0) return null;
  return parameters;
}

/**
 * How the active set runs: as the search it records, as its genes, or not at
 * all. A search is re-run only when the set records the parameters it ran with.
 */
export function experimentBasis(geneSet: GeneSet): ExperimentBasis {
  const searchName = recordedSearch(geneSet);
  const parameters = recordedParameters(geneSet);
  if (searchName !== null && parameters !== null) {
    return { kind: "search", searchName, parameters };
  }
  if (geneSet.geneIds.length > 0) {
    return { kind: "geneList", geneIds: geneSet.geneIds };
  }
  return { kind: "none" };
}

/** Why no experiment can run over this set, or null when one can. */
export function experimentBlocked(basis: ExperimentBasis): string | null {
  return basis.kind === "none" ? NOTHING_TO_RUN : null;
}

/** Why an organism changes nothing for this set, or null when it varies it. */
export function organismBlocked(geneSet: GeneSet): string | null {
  const basis = experimentBasis(geneSet);
  if (basis.kind === "search") return null;
  if (basis.kind === "none") return NOTHING_TO_RUN;
  if ((geneSet.searchName ?? "").startsWith(COMBINE_STEP_PREFIX)) {
    return (
      "This set was saved from a step that combines two others, which runs no " +
      "search of its own, so an organism changes nothing."
    );
  }
  const searchName = recordedSearch(geneSet);
  if (searchName !== null) {
    return (
      `This set records the search ${searchName} but not the parameters ` +
      "it ran with, so there is nothing for an organism to vary."
    );
  }
  return (
    "This set holds a fixed gene list and records no search, so an organism " +
    "changes nothing. Evaluate or Benchmark it instead."
  );
}

/** The three runs a panel starts over a saved set. */
export type ExperimentRun = "evaluation" | "batch" | "benchmark";

// CreateExperimentRequest.name accepts 200 characters, and a set name may
// already be 200 of its own.
const NAME_MAX_LENGTH = 200;
const TRUNCATION_MARK = "...";

/** The run's name, kept inside the length the API accepts. */
export function experimentName(setName: string, run: ExperimentRun): string {
  const suffix = ` (${run})`;
  const room = NAME_MAX_LENGTH - suffix.length;
  if (setName.length <= room) return `${setName}${suffix}`;
  const head = setName.slice(0, room - TRUNCATION_MARK.length);
  return `${head}${TRUNCATION_MARK}${suffix}`;
}

export interface ExperimentBaseArgs {
  geneSet: GeneSet;
  positiveControls: string[];
  negativeControls: string[];
  run: ExperimentRun;
}

/**
 * The request every experiment over a saved set starts from.
 *
 * One builder keeps the controls search, the record type, the name length and
 * the gene-set link on every panel's request.
 */
export function experimentBase({
  geneSet,
  positiveControls,
  negativeControls,
  run,
}: ExperimentBaseArgs): CreateExperimentRequest {
  const basis = experimentBasis(geneSet);
  return {
    siteId: geneSet.siteId,
    recordType: geneSet.recordType ?? "gene",
    mode: "single",
    searchName: basis.kind === "search" ? basis.searchName : "",
    parameters: basis.kind === "search" ? basis.parameters : {},
    positiveControls,
    negativeControls,
    controlsSearchName: CONTROLS_SEARCH_NAME,
    controlsParamName: CONTROLS_PARAM_NAME,
    targetGeneIds: basis.kind === "geneList" ? basis.geneIds : null,
    name: experimentName(geneSet.name, run),
    geneSetId: geneSet.id,
  };
}
