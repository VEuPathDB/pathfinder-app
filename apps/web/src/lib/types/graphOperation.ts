import type {
  CombineOp,
  ColocationParams,
  Step,
  StrategyStepNode,
} from "@pathfinder/shared";
import type { ParamValueMap } from "@/lib/parameters/paramValue";

type AttachPoint =
  | { mode: "new-root" }
  | { mode: "into-slot"; targetStepId: string; slot: "primary" | "secondary" };

export type DeleteResolution =
  | "collapse-combine"
  | "orphan-sibling"
  | "delete-subtree"
  | "promote-primary"
  | "delete-strategy";

export type DeleteEdgeResolution = "detach" | "collapse";

export type GraphOperation =
  | { kind: "addLeaf"; step: Step; attach: AttachPoint }
  | { kind: "addCombine"; step: Step; leftId: string; rightId: string }
  | {
      kind: "addTransform";
      step: Step;
      inputId: string;
      mode: "before-consumer" | "new-root";
    }
  | {
      kind: "duplicateStep";
      sourceStepId: string;
      duplicateStepId: string;
      combineStepId: string;
      combineDisplayName?: string;
    }
  | { kind: "deleteStep"; stepId: string; resolution: DeleteResolution }
  | {
      kind: "deleteEdge";
      sourceId: string;
      targetId: string;
      slot: "primary" | "secondary";
      resolution: DeleteEdgeResolution;
    }
  | {
      kind: "updateStepParams";
      stepId: string;
      parameters: ParamValueMap;
    }
  | {
      kind: "updateCombineOperator";
      stepId: string;
      operator: CombineOp;
      colocationParams?: ColocationParams | null;
    }
  | { kind: "updateStepMeta"; stepId: string; displayName: string }
  | {
      kind: "updateStrategyMeta";
      name?: string;
      description?: string | null;
    }
  | {
      kind: "wireInput";
      targetStepId: string;
      slot: "primary" | "secondary";
      sourceStepId: string;
    }
  | {
      kind: "replaceStrategy";
      root: StrategyStepNode;
      name?: string;
      description?: string | null;
    };
