export { applyOperation } from "./apply";
export type { ApplyResult, OperationChoice } from "./types";
export type {
  DeleteEdgeResolution,
  DeleteResolution,
  GraphOperation,
} from "@/lib/types/graphOperation";
export { computeDeleteChoices } from "./deleteResolutions";
export { walkSubtreeIds } from "./utils";
