import type { Strategy } from "@pathfinder/shared";
import type {
  DeleteEdgeResolution,
  DeleteResolution,
} from "@/lib/types/graphOperation";

export interface OperationChoice<R extends string = string> {
  resolution: R;
  title: string;
  description: string;
  isDefault: boolean;
  willDelete: string[];
}

export type ApplyResult =
  | { kind: "applied"; next: Strategy; description: string }
  | {
      kind: "needs-choice";
      choices: OperationChoice<DeleteResolution | DeleteEdgeResolution>[];
    }
  | { kind: "rejected"; reason: string };
